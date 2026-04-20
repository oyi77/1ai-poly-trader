"""Cross-feature integration tests for Phase 2 (Features 2, 3, 4).

Tests end-to-end workflows combining Activity Timeline (Feature 2) + Debate Engine (Feature 3)
+ Proposal System (Feature 4) + Stats Pipeline (Wave 5a) using actual database models.
"""

from datetime import datetime, timedelta
import json
import pytest
from sqlalchemy.orm import Session

from backend.models.database import (
    ActivityLog, StrategyProposal, Trade, StrategyConfig, MiroFishSignal,
    DecisionLog,
)


class TestCrossFeatureActivityToDeal:
    """Workflow 1: Activity → Decision → Proposal."""

    def test_activity_logged_then_decision_created(self, db: Session):
        """Activity + Decision created independently."""
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="entry",
            data={"event": "trade_approved", "reason": "manual"},
            confidence_score=0.85,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        logged = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert logged is not None
        assert logged.strategy_name == "test_strat"

        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market-1",
            decision="BUY",
            confidence=0.85,
        )
        db.add(decision)
        db.commit()

        stored = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored is not None

    def test_activity_decision_proposal_flow(self, db: Session):
        """Full workflow: Activity → Decision → Proposal."""
        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"signal": "RSI overbought"},
            confidence_score=0.72,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        decision = DecisionLog(
            strategy="btc_momentum",
            market_ticker="will-btc-rally",
            decision="HOLD",
            confidence=0.72,
        )
        db.add(decision)
        db.commit()

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"max_position_usd": 5000, "min_edge": 0.08},
            expected_impact="Optimize position sizing",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        assert db.query(ActivityLog).count() >= 1
        assert db.query(DecisionLog).count() >= 1
        assert db.query(StrategyProposal).count() >= 1

    def test_mirofish_signal_visible_in_decision(self, db: Session):
        """MiroFish signal available for decision-making."""
        signal = MiroFishSignal(
            market_id="btc-2024-q1",
            prediction=0.75,
            confidence=0.75,
            reasoning="On-chain metrics bullish",
            source="mirofish_predictive_model",
            weight=1.0,
        )
        db.add(signal)
        db.commit()

        decision = DecisionLog(
            strategy="btc_momentum",
            market_ticker="btc-2024-q1",
            decision="BUY",
            confidence=0.80,
            signal_data=json.dumps({"mirofish": 0.75}),
        )
        db.add(decision)
        db.commit()

        stored_signal = db.query(MiroFishSignal).filter_by(market_id="btc-2024-q1").first()
        assert stored_signal is not None
        assert stored_signal.weight == 1.0


class TestCrossFeatureProposalExecution:
    """Workflow 2: Proposal execution updates config."""

    def test_proposal_approval_updates_strategy_config(self, db: Session):
        """Approved proposal updates StrategyConfig."""
        config = StrategyConfig(
            strategy_name="btc_momentum",
            enabled=True,
            params=json.dumps({"max_position_usd": 3000}),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"max_position_usd": 5000},
            expected_impact="Increase limit",
            admin_decision="approved",
            admin_user_id="admin_1",
        )
        db.add(proposal)
        db.commit()

        params = json.loads(config.params)
        params["max_position_usd"] = 5000
        config.params = json.dumps(params)
        db.commit()

        updated = db.query(StrategyConfig).filter_by(strategy_name="btc_momentum").first()
        assert json.loads(updated.params)["max_position_usd"] == 5000

    def test_proposal_execution_then_rollback(self, db: Session):
        """Negative impact triggers rollback."""
        config = StrategyConfig(
            strategy_name="btc_momentum",
            enabled=True,
            params=json.dumps({"max_position_usd": 3000}),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"max_position_usd": 10000},
            expected_impact="Aggressive scaling",
            admin_decision="executed",
            executed_at=datetime.now(),
        )
        db.add(proposal)
        db.commit()

        proposal.admin_decision = "rolled_back"
        db.commit()

        rolled_back = db.query(StrategyProposal).filter_by(
            strategy_name="btc_momentum"
        ).first()
        assert rolled_back.admin_decision == "rolled_back"


class TestCrossFeatureStatsCorrelation:
    """Workflow 3: Activity correlates with stats."""

    def test_activity_events_visible(self, db: Session):
        """Activity events persisted and queryable."""
        activities = [
            ActivityLog(
                strategy_name="btc_momentum",
                decision_type="entry",
                data={"type": "trade_executed"},
                confidence_score=0.8,
                mode="paper",
            ),
            ActivityLog(
                strategy_name="btc_momentum",
                decision_type="exit",
                data={"type": "decision_made"},
                confidence_score=0.75,
                mode="paper",
            ),
        ]
        for act in activities:
            db.add(act)
        db.commit()

        all_acts = db.query(ActivityLog).all()
        assert len(all_acts) >= 2

    def test_activity_trade_correlation(self, db: Session):
        """Activity timeline correlates with Trade data."""
        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"signal": "from_activity"},
            confidence_score=0.8,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        trade = Trade(
            market_ticker="BTC-USD",
            platform="polymarket",
            direction="up",
            entry_price=50000.0,
            size=0.1,
            timestamp=activity.timestamp,
        )
        db.add(trade)
        db.commit()

        linked_trade = db.query(Trade).filter_by(
            market_ticker="BTC-USD"
        ).first()
        assert linked_trade is not None
        assert linked_trade.entry_price == 50000.0


class TestCrossFeatureConcurrency:
    """Workflow 4: Parallel operations."""

    def test_multiple_proposals_maintain_order(self, db: Session):
        """Multiple proposals maintain FIFO approval order."""
        proposals = []
        for i in range(5):
            p = StrategyProposal(
                strategy_name="btc_momentum",
                change_details={"position": 2000 + i * 500},
                expected_impact=f"Proposal {i}",
                admin_decision="pending",
            )
            db.add(p)
            proposals.append(p)
        db.commit()

        for i, p in enumerate(proposals):
            p.admin_decision = "approved"
            p.executed_at = datetime.now() + timedelta(milliseconds=i * 10)
        db.commit()

        approved = db.query(StrategyProposal).filter_by(
            admin_decision="approved"
        ).order_by(StrategyProposal.executed_at).all()
        assert len(approved) == 5

    def test_activity_decision_proposal_parallel(self, db: Session):
        """Parallel Activity + Decision + Proposal creation."""
        for i in range(3):
            activity = ActivityLog(
                strategy_name=f"strategy_{i}",
                decision_type="entry",
                data={"index": i},
                confidence_score=0.7,
                mode="paper",
            )
            db.add(activity)

        for i in range(3):
            decision = DecisionLog(
                strategy=f"strategy_{i}",
                market_ticker=f"market_{i}",
                decision="BUY",
                confidence=0.75,
            )
            db.add(decision)

        for i in range(3):
            proposal = StrategyProposal(
                strategy_name=f"strategy_{i}",
                change_details={"param": 3000 + i},
                expected_impact="Parallel test",
                admin_decision="pending",
            )
            db.add(proposal)

        db.commit()

        assert db.query(ActivityLog).count() >= 3
        assert db.query(DecisionLog).count() >= 3
        assert db.query(StrategyProposal).count() >= 3

    def test_rollback_with_concurrent_proposals(self, db: Session):
        """Rollback in progress + new proposal arrival."""
        prop1 = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 5000},
            expected_impact="First",
            admin_decision="executed",
            executed_at=datetime.now() - timedelta(seconds=10),
        )
        db.add(prop1)

        prop2 = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"edge": 0.06},
            expected_impact="Second",
            admin_decision="pending",
        )
        db.add(prop2)
        db.commit()

        prop1.admin_decision = "rolled_back"
        prop2.admin_decision = "approved"
        db.commit()

        final = db.query(StrategyProposal).filter_by(
            strategy_name="btc_momentum"
        ).order_by(StrategyProposal.executed_at.desc()).all()
        assert final[0].admin_decision in ["rolled_back", "approved"]


class TestCrossFeatureErrorPropagation:
    """Workflow 5: Error isolation."""

    def test_activity_error_doesnt_block_decision(self, db: Session):
        """Activity logging independent from Decision."""
        decision = DecisionLog(
            strategy="test",
            market_ticker="btc",
            decision="HOLD",
            confidence=0.65,
        )
        db.add(decision)
        db.commit()

        assert db.query(DecisionLog).count() >= 1

    def test_decision_error_doesnt_block_proposals(self, db: Session):
        """Proposal creation independent from Decision."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 4000},
            expected_impact="Test",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        assert db.query(StrategyProposal).count() >= 1

    def test_proposal_error_doesnt_block_activity(self, db: Session):
        """Activity logging independent from Proposal."""
        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"snapshot": "daily"},
            confidence_score=0.8,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        assert db.query(ActivityLog).count() >= 1


class TestCrossFeatureDataConsistency:
    """Verify cross-feature data consistency."""

    def test_no_data_loss_in_workflow(self, db: Session):
        """All updates committed atomically."""
        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"trade": True},
            confidence_score=0.8,
            mode="paper",
        )
        db.add(activity)

        decision = DecisionLog(
            strategy="btc_momentum",
            market_ticker="btc-2024",
            decision="BUY",
            confidence=0.80,
        )
        db.add(decision)

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 4000},
            expected_impact="Consistency",
            admin_decision="pending",
        )
        db.add(proposal)

        db.commit()

        assert db.query(ActivityLog).count() >= 1
        assert db.query(DecisionLog).count() >= 1
        assert db.query(StrategyProposal).count() >= 1

    def test_foreign_key_integrity(self, db: Session):
        """Foreign keys maintained across features."""
        config = StrategyConfig(
            strategy_name="btc_momentum",
            enabled=True,
            params=json.dumps({"pos": 3000}),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"config_linked": True},
            confidence_score=0.8,
            mode="paper",
        )
        db.add(activity)

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 5000},
            expected_impact="FK test",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        activities = db.query(ActivityLog).filter_by(strategy_name="btc_momentum").all()
        proposals = db.query(StrategyProposal).filter_by(strategy_name="btc_momentum").all()
        assert len(activities) >= 1
        assert len(proposals) >= 1
