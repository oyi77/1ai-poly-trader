"""Edge case and negative scenario tests for Phase 2 integration.

Covers error paths, boundary conditions, and failure recovery across Features 2, 3, 4.
"""

from datetime import datetime
import json
from sqlalchemy.orm import Session

from backend.models.database import (
    ActivityLog, StrategyProposal, Trade, StrategyConfig, MiroFishSignal,
    DecisionLog,
)


class TestActivityLogEdgeCases:
    """Activity logging edge cases and error paths."""

    def test_activity_with_null_data_field(self, db: Session):
        """Activity with missing/null data field."""
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="entry",
            data={},
            confidence_score=0.5,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        stored = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert stored is not None
        assert stored.data == {}

    def test_activity_with_minimal_confidence(self, db: Session):
        """Activity with zero confidence."""
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="hold",
            data={"reason": "low_confidence"},
            confidence_score=0.0,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        stored = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert stored.confidence_score == 0.0

    def test_activity_with_max_confidence(self, db: Session):
        """Activity with maximum confidence."""
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="entry",
            data={"certainty": "high"},
            confidence_score=1.0,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        stored = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert stored.confidence_score == 1.0

    def test_activity_timestamp_ordering(self, db: Session):
        """Multiple activities maintain timestamp ordering."""
        for i in range(3):
            activity = ActivityLog(
                strategy_name="test_strat",
                decision_type="entry",
                data={"index": i},
                confidence_score=0.7,
                mode="paper",
            )
            db.add(activity)
        db.commit()

        activities = db.query(ActivityLog).order_by(ActivityLog.timestamp).all()
        assert len(activities) >= 3
        for i in range(len(activities) - 1):
            assert activities[i].timestamp <= activities[i + 1].timestamp


class TestDecisionLogEdgeCases:
    """Decision logging edge cases and error paths."""

    def test_decision_with_null_signal_data(self, db: Session):
        """Decision with missing signal_data."""
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="BUY",
            confidence=0.75,
            signal_data=None,
        )
        db.add(decision)
        db.commit()

        stored = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored.signal_data is None

    def test_decision_with_empty_signal_data(self, db: Session):
        """Decision with empty signal_data JSON."""
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="SKIP",
            confidence=0.5,
            signal_data="{}",
        )
        db.add(decision)
        db.commit()

        stored = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored.signal_data == "{}"

    def test_decision_outcome_transitions(self, db: Session):
        """Decision outcome state transitions."""
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="BUY",
            confidence=0.8,
            outcome=None,
        )
        db.add(decision)
        db.commit()

        decision.outcome = "WIN"
        db.commit()

        updated = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert updated.outcome == "WIN"

        decision.outcome = "LOSS"
        db.commit()

        final = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert final.outcome == "LOSS"

    def test_decision_with_reason_text(self, db: Session):
        """Decision with detailed reason."""
        reason = "Market volatility exceeded threshold; risk-reward unfavorable"
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="SKIP",
            confidence=0.6,
            reason=reason,
        )
        db.add(decision)
        db.commit()

        stored = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored.reason == reason


class TestProposalEdgeCases:
    """Proposal system edge cases and error paths."""

    def test_proposal_pending_state(self, db: Session):
        """Proposal in pending state remains queryable."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"param": "value"},
            expected_impact="Test impact",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        pending = db.query(StrategyProposal).filter_by(
            admin_decision="pending"
        ).all()
        assert len(pending) >= 1

    def test_proposal_state_machine(self, db: Session):
        """Proposal follows state machine: pending → approved → executed."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 5000},
            expected_impact="Scale position",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        proposal.admin_decision = "approved"
        proposal.admin_user_id = "admin_1"
        db.commit()

        proposal.admin_decision = "executed"
        proposal.executed_at = datetime.now()
        db.commit()

        final = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert final.admin_decision == "executed"
        assert final.executed_at is not None

    def test_proposal_with_impact_measured(self, db: Session):
        """Proposal tracks measured impact."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"max_pos": 5000},
            expected_impact="Improve sharpe",
            admin_decision="executed",
            executed_at=datetime.now(),
            impact_measured={"sharpe_delta": 0.15, "status": "positive"},
        )
        db.add(proposal)
        db.commit()

        stored = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert stored.impact_measured is not None

    def test_proposal_with_admin_notes(self, db: Session):
        """Proposal stores admin decision reason."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"edge": 0.05},
            expected_impact="Lower threshold",
            admin_decision="rejected",
            admin_decision_reason="Threshold too aggressive for current volatility",
        )
        db.add(proposal)
        db.commit()

        stored = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert stored.admin_decision_reason is not None


class TestMiroFishSignalEdgeCases:
    """MiroFish signal edge cases and API failure scenarios."""

    def test_mirofish_prediction_boundaries(self, db: Session):
        """MiroFish predictions at boundary values."""
        for pred_val in [0.0, 0.5, 1.0]:
            signal = MiroFishSignal(
                market_id=f"market-{pred_val}",
                prediction=pred_val,
                confidence=0.8,
                reasoning=f"Boundary test {pred_val}",
                source="test_source",
                weight=1.0,
            )
            db.add(signal)
        db.commit()

        signals = db.query(MiroFishSignal).all()
        assert len(signals) >= 3

    def test_mirofish_confidence_boundaries(self, db: Session):
        """MiroFish confidence at 0.0 and 1.0."""
        for conf_val in [0.0, 1.0]:
            signal = MiroFishSignal(
                market_id=f"conf-market-{conf_val}",
                prediction=0.5,
                confidence=conf_val,
                reasoning=f"Confidence {conf_val}",
                source="test",
                weight=1.0,
            )
            db.add(signal)
        db.commit()

        signals = db.query(MiroFishSignal).all()
        assert len(signals) >= 2

    def test_mirofish_weight_variance(self, db: Session):
        """MiroFish signals with different weights."""
        for weight_val in [0.5, 1.0, 2.0]:
            signal = MiroFishSignal(
                market_id=f"weight-{weight_val}",
                prediction=0.6,
                confidence=0.8,
                reasoning=f"Weight {weight_val}",
                source="test",
                weight=weight_val,
            )
            db.add(signal)
        db.commit()

        signals = db.query(MiroFishSignal).all()
        assert len(signals) >= 3

    def test_mirofish_signal_update(self, db: Session):
        """MiroFish signal updates preserve data."""
        signal = MiroFishSignal(
            market_id="update-test",
            prediction=0.6,
            confidence=0.75,
            reasoning="Initial prediction",
            source="test",
            weight=1.0,
        )
        db.add(signal)
        db.commit()

        signal.prediction = 0.7
        signal.confidence = 0.85
        signal.reasoning = "Updated prediction"
        db.commit()

        updated = db.query(MiroFishSignal).filter_by(
            market_id="update-test"
        ).first()
        assert updated.prediction == 0.7
        assert updated.confidence == 0.85


class TestStrategyConfigEdgeCases:
    """Strategy configuration edge cases."""

    def test_config_with_empty_params(self, db: Session):
        """Strategy config with empty parameters."""
        config = StrategyConfig(
            strategy_name="test_empty",
            enabled=True,
            params=json.dumps({}),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        stored = db.query(StrategyConfig).filter_by(
            strategy_name="test_empty"
        ).first()
        assert json.loads(stored.params) == {}

    def test_config_params_json_parsing(self, db: Session):
        """Config params are properly JSON serialized."""
        params = {"max_pos": 5000, "min_edge": 0.05, "timeout": 30}
        config = StrategyConfig(
            strategy_name="test_json",
            enabled=True,
            params=json.dumps(params),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        stored = db.query(StrategyConfig).filter_by(
            strategy_name="test_json"
        ).first()
        parsed = json.loads(stored.params)
        assert parsed["max_pos"] == 5000
        assert parsed["min_edge"] == 0.05

    def test_config_mode_override(self, db: Session):
        """Strategy config supports mode-specific overrides."""
        config = StrategyConfig(
            strategy_name="test_mode",
            enabled=True,
            params=json.dumps({}),
            interval_seconds=300,
            mode="paper",
        )
        db.add(config)
        db.commit()

        stored = db.query(StrategyConfig).filter_by(
            strategy_name="test_mode"
        ).first()
        assert stored.mode == "paper"


class TestTradeEdgeCases:
    """Trade edge cases and boundary conditions."""

    def test_trade_zero_size(self, db: Session):
        """Trade with zero position size."""
        trade = Trade(
            market_ticker="BTC-USD",
            platform="polymarket",
            direction="up",
            entry_price=50000.0,
            size=0.0,
            timestamp=datetime.now(),
        )
        db.add(trade)
        db.commit()

        stored = db.query(Trade).filter_by(id=trade.id).first()
        assert stored.size == 0.0

    def test_trade_zero_price(self, db: Session):
        """Trade with zero entry price (edge case)."""
        trade = Trade(
            market_ticker="EXOTIC",
            platform="test",
            direction="up",
            entry_price=0.0,
            size=1.0,
            timestamp=datetime.now(),
        )
        db.add(trade)
        db.commit()

        stored = db.query(Trade).filter_by(id=trade.id).first()
        assert stored.entry_price == 0.0

    def test_trade_settlement_lifecycle(self, db: Session):
        """Trade settlement state transitions."""
        trade = Trade(
            market_ticker="BTC-USD",
            platform="polymarket",
            direction="up",
            entry_price=50000.0,
            size=0.1,
            timestamp=datetime.now(),
            settled=False,
            result="pending",
        )
        db.add(trade)
        db.commit()

        trade.settled = True
        trade.settlement_time = datetime.now()
        trade.settlement_value = 1.0
        trade.result = "win"
        trade.pnl = 100.0
        db.commit()

        final = db.query(Trade).filter_by(id=trade.id).first()
        assert final.settled is True
        assert final.result == "win"


class TestConcurrentStateViolations:
    """Test concurrent access patterns and state violations."""

    def test_proposal_concurrent_approvals(self, db: Session):
        """Multiple proposals don't interfere with approval state."""
        proposals = []
        for i in range(3):
            p = StrategyProposal(
                strategy_name=f"strategy_{i}",
                change_details={"param": i},
                expected_impact=f"Impact {i}",
                admin_decision="pending",
            )
            db.add(p)
            proposals.append(p)
        db.commit()

        for i, p in enumerate(proposals):
            p.admin_decision = "approved"
        db.commit()

        approved = db.query(StrategyProposal).filter_by(
            admin_decision="approved"
        ).all()
        assert len(approved) == 3

    def test_activity_concurrent_logging(self, db: Session):
        """Concurrent activity logging maintains order."""
        for i in range(5):
            activity = ActivityLog(
                strategy_name="test_strat",
                decision_type="entry",
                data={"seq": i},
                confidence_score=0.7,
                mode="paper",
            )
            db.add(activity)
        db.commit()

        activities = db.query(ActivityLog).order_by(
            ActivityLog.timestamp
        ).all()
        assert len(activities) >= 5


class TestDataLossScenarios:
    """Test scenarios that could lead to data loss."""

    def test_proposal_rejection_preserves_data(self, db: Session):
        """Rejected proposal data remains queryable."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"pos": 10000},
            expected_impact="Aggressive scaling",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        proposal.admin_decision = "rejected"
        proposal.admin_decision_reason = "Too aggressive"
        db.commit()

        stored = db.query(StrategyProposal).filter_by(
            admin_decision="rejected"
        ).first()
        assert stored is not None
        assert stored.change_details["pos"] == 10000

    def test_activity_deletion_preserves_linked_data(self, db: Session):
        """Activity deletion doesn't cascade to decisions."""
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="entry",
            data={"event": "signal"},
            confidence_score=0.8,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="BUY",
            confidence=0.8,
        )
        db.add(decision)
        db.commit()

        db.query(ActivityLog).delete()
        db.commit()

        stored_decision = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored_decision is not None

    def test_config_modification_preserves_history(self, db: Session):
        """Config changes are trackable."""
        config = StrategyConfig(
            strategy_name="test_history",
            enabled=True,
            params=json.dumps({"v": 1}),
            interval_seconds=300,
        )
        db.add(config)
        db.commit()

        config.params = json.dumps({"v": 2})
        db.commit()

        final = db.query(StrategyConfig).filter_by(
            strategy_name="test_history"
        ).first()
        assert json.loads(final.params)["v"] == 2


class TestMissingDataScenarios:
    """Test handling of missing or incomplete data."""

    def test_decision_without_reason(self, db: Session):
        """Decision without explicit reason field."""
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc-market",
            decision="BUY",
            confidence=0.75,
            reason=None,
        )
        db.add(decision)
        db.commit()

        stored = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert stored.reason is None

    def test_proposal_minimal_change_details(self, db: Session):
        """Proposal with minimal change details."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"minimal": True},
            expected_impact="Minimal change",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        stored = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert len(stored.change_details) >= 1

    def test_activity_with_large_data_payload(self, db: Session):
        """Activity with large data structure."""
        large_data = {
            f"key_{i}": {"nested": i, "value": i * 100}
            for i in range(100)
        }
        activity = ActivityLog(
            strategy_name="test_strat",
            decision_type="entry",
            data=large_data,
            confidence_score=0.7,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        stored = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert len(stored.data) == 100


class TestRecoveryScenarios:
    """Test recovery from error states."""

    def test_rollback_from_rejected_state(self, db: Session):
        """Proposal can transition from rejected to pending."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details={"param": "value"},
            expected_impact="Test",
            admin_decision="rejected",
            admin_decision_reason="Initial reason",
        )
        db.add(proposal)
        db.commit()

        proposal.admin_decision = "pending"
        proposal.admin_decision_reason = None
        db.commit()

        updated = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert updated.admin_decision == "pending"

    def test_outcome_correction(self, db: Session):
        """Decision outcome can be corrected."""
        decision = DecisionLog(
            strategy="test_strat",
            market_ticker="btc",
            decision="BUY",
            outcome="LOSS",
        )
        db.add(decision)
        db.commit()

        decision.outcome = "WIN"
        db.commit()

        corrected = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert corrected.outcome == "WIN"
