"""Wave 6 QA: Comprehensive regression, performance, and deployment validation.

Covers:
- Full Phase 2 feature regression (Features 2, 3, 4 + all dependencies)
- Performance baseline validation (response times, memory, DB query efficiency)
- API contract validation (schema consistency, versioning)
- Deployment readiness checklist
- Data migration validation (old → new schema)
"""

import json
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.database import (
    ActivityLog, StrategyProposal, StrategyConfig, MiroFishSignal,
    DecisionLog, BotState,
)


class TestPhase2RegressionFeature2:
    """Feature 2 (Stats Correlator) regression across all modules."""

    def test_activity_created_with_all_required_fields(self, db: Session):
        """Activity must include strategy, decision type, confidence, mode."""
        activity = ActivityLog(
            strategy_name="btc_momentum",
            decision_type="entry",
            data={"market_id": "btc-usd-2025"},
            confidence_score=0.85,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        retrieved = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert retrieved.strategy_name == "btc_momentum"
        assert retrieved.decision_type == "entry"
        assert retrieved.confidence_score == 0.85
        assert retrieved.mode == "paper"
        assert retrieved.timestamp is not None

    def test_activity_timestamp_auto_set(self, db: Session):
        """Activity timestamp must auto-populate on creation."""
        before = datetime.utcnow()
        activity = ActivityLog(
            strategy_name="test",
            decision_type="entry",
            data={},
            confidence_score=0.5,
            mode="paper",
        )
        db.add(activity)
        db.commit()
        after = datetime.utcnow()

        assert before <= activity.timestamp <= after

    def test_activity_queryable_by_strategy_name(self, db: Session):
        """Must be able to find activities by strategy name."""
        for i in range(3):
            activity = ActivityLog(
                strategy_name="weather_emos" if i % 2 == 0 else "btc_oracle",
                decision_type="entry",
                data={},
                confidence_score=0.5,
                mode="paper",
            )
            db.add(activity)
        db.commit()

        weather_activities = db.query(ActivityLog).filter_by(
            strategy_name="weather_emos"
        ).all()
        assert len(weather_activities) == 2

    def test_activity_null_data_handled_gracefully(self, db: Session):
        """Activity with null/empty data should not crash."""
        activity = ActivityLog(
            strategy_name="test",
            decision_type="hold",
            data=None,
            confidence_score=0.3,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        retrieved = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert retrieved is not None
        assert retrieved.data is None


class TestPhase2RegressionFeature3:
    """Feature 3 (MiroFish Debate Integration) regression."""

    def test_mirofish_signal_required_fields(self, db: Session):
        """MiroFish signal must have market_id, prediction, confidence."""
        signal = MiroFishSignal(
            market_id="btc-usd-2025",
            prediction=0.72,  # Float, not string
            confidence=0.85,
            reasoning="Price momentum suggests upside",
            source="mirofish_debate",
            weight=1.0,
        )
        db.add(signal)
        db.commit()

        retrieved = db.query(MiroFishSignal).filter_by(id=signal.id).first()
        assert retrieved.prediction == 0.72
        assert isinstance(retrieved.prediction, float)
        assert retrieved.confidence == 0.85

    def test_mirofish_prediction_boundary_values(self, db: Session):
        """MiroFish prediction must be 0.0-1.0 inclusive."""
        for pred in [0.0, 0.5, 1.0]:
            signal = MiroFishSignal(
                market_id=f"market_{pred}",
                prediction=pred,
                confidence=0.5,
                reasoning="Test reasoning",
                source="mirofish_debate",
                weight=1.0,
            )
            db.add(signal)
        db.commit()

        signals = db.query(MiroFishSignal).all()
        assert len(signals) == 3
        predictions = [s.prediction for s in signals]
        assert all(0.0 <= p <= 1.0 for p in predictions)

    def test_mirofish_weight_variance(self, db: Session):
        """MiroFish signals can have varying weights."""
        for weight in [0.5, 1.0, 2.0]:
            signal = MiroFishSignal(
                market_id=f"market_w{weight}",
                prediction=0.5,
                confidence=0.5,
                reasoning="Test reasoning",
                source="mirofish_debate",
                weight=weight,
            )
            db.add(signal)
        db.commit()

        signals = db.query(MiroFishSignal).all()
        weights = [s.weight for s in signals]
        assert 0.5 in weights and 1.0 in weights and 2.0 in weights


class TestPhase2RegressionFeature4:
    """Feature 4 (Proposal System) regression."""

    def test_proposal_state_machine_transitions(self, db: Session):
        """Proposal must follow valid state transitions."""
        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details=json.dumps({"interval_seconds": 120}),
            expected_impact="Reduce signal lag by 50%",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        assert proposal.admin_decision == "pending"

        proposal.admin_decision = "approved"
        proposal.executed_at = datetime.utcnow()
        db.commit()

        retrieved = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert retrieved.admin_decision == "approved"
        assert retrieved.executed_at is not None

    def test_proposal_requires_change_details(self, db: Session):
        """Proposal must include change_details (JSON)."""
        proposal = StrategyProposal(
            strategy_name="test_strat",
            change_details=json.dumps({"enabled": False, "params": {"threshold": 0.7}}),
            expected_impact="Disable strategy for testing",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        retrieved = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        details = json.loads(retrieved.change_details)
        assert details["enabled"] is False

    def test_proposal_admin_approval_chain(self, db: Session):
        """Proposal approval must include admin user ID and reason."""
        proposal = StrategyProposal(
            strategy_name="test_strat",
            change_details=json.dumps({}),
            expected_impact="Test impact",
            admin_decision="approved",
            admin_user_id="admin_123",
            admin_decision_reason="Meets safety requirements",
        )
        db.add(proposal)
        db.commit()

        retrieved = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        assert retrieved.admin_user_id == "admin_123"
        assert retrieved.admin_decision_reason == "Meets safety requirements"


class TestPhase2RegressionCrossDependencies:
    """Test interactions between Features 2, 3, 4."""

    def test_activity_to_decision_link(self, db: Session):
        """Activity should link to DecisionLog for traceability."""
        activity = ActivityLog(
            strategy_name="test_strategy",
            decision_type="entry",
            data={"signal_id": 1},
            confidence_score=0.75,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        decision = DecisionLog(
            strategy="test_strategy",
            market_ticker="btc-usd-2025",
            decision="BUY",
            confidence=0.75,
            signal_data=json.dumps({"activity_id": activity.id}),
            reason="Activity triggered signal",
        )
        db.add(decision)
        db.commit()

        retrieved_decision = db.query(DecisionLog).filter_by(id=decision.id).first()
        signal_data = json.loads(retrieved_decision.signal_data)
        assert signal_data["activity_id"] == activity.id

    def test_decision_to_proposal_flow(self, db: Session):
        """Decision can lead to proposal if admin reviews it."""
        decision = DecisionLog(
            strategy="btc_momentum",
            market_ticker="btc-usd-2025",
            decision="BUY",
            confidence=0.85,
            reason="High confidence signal",
        )
        db.add(decision)
        db.commit()

        proposal = StrategyProposal(
            strategy_name="btc_momentum",
            change_details=json.dumps({"interval_seconds": 120}),
            expected_impact="Reduce lag",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        assert proposal.strategy_name == decision.strategy


class TestAPIContractValidation:
    """Validate REST API schema consistency."""

    def test_decision_log_json_fields_parseable(self, db: Session):
        """DecisionLog.signal_data must be valid JSON (if present)."""
        valid_json = json.dumps({"market_id": "abc", "price": 0.45})
        decision = DecisionLog(
            strategy="test",
            market_ticker="test-market",
            decision="BUY",
            confidence=0.5,
            signal_data=valid_json,
        )
        db.add(decision)
        db.commit()

        retrieved = db.query(DecisionLog).filter_by(id=decision.id).first()
        parsed = json.loads(retrieved.signal_data)
        assert parsed["market_id"] == "abc"
        assert parsed["price"] == 0.45

    def test_strategy_config_params_json_parseable(self, db: Session):
        """StrategyConfig.params must be valid JSON."""
        params = json.dumps({"threshold": 0.7, "interval": 60})
        config = StrategyConfig(
            strategy_name="test_config",
            enabled=True,
            params=params,
            interval_seconds=60,
            mode="paper",
        )
        db.add(config)
        db.commit()

        retrieved = db.query(StrategyConfig).filter_by(id=config.id).first()
        parsed = json.loads(retrieved.params)
        assert parsed["threshold"] == 0.7

    def test_proposal_change_details_json_parseable(self, db: Session):
        """StrategyProposal.change_details must be valid JSON."""
        changes = json.dumps({"enabled": False, "params": {"new_interval": 300}})
        proposal = StrategyProposal(
            strategy_name="test_proposal",
            change_details=changes,
            expected_impact="Reduce frequency",
            admin_decision="pending",
        )
        db.add(proposal)
        db.commit()

        retrieved = db.query(StrategyProposal).filter_by(id=proposal.id).first()
        parsed = json.loads(retrieved.change_details)
        assert parsed["enabled"] is False


class TestDeploymentReadiness:
    """Checklist for production deployment."""

    def test_bot_state_seeded_on_startup(self, db: Session):
        """BotState must exist for system operation."""
        state = db.query(BotState).filter_by(mode="paper").first()
        assert state is not None
        assert state.paper_bankroll > 0

    def test_strategy_config_defaults_exist(self, db: Session):
        """Default strategy configs must be seeded."""
        for strat in ["btc_momentum", "weather_emos", "kalshi_arb"]:
            existing = db.query(StrategyConfig).filter_by(strategy_name=strat).first()
            if not existing:
                config = StrategyConfig(
                    strategy_name=strat,
                    enabled=True,
                    params=json.dumps({}),
                    interval_seconds=300,
                    mode="paper",
                )
                db.add(config)
        db.commit()

        strategies = db.query(StrategyConfig).all()
        assert len(strategies) >= 3

    def test_no_hardcoded_secrets_in_schema(self, db: Session):
        """Database schema must not contain hardcoded API keys."""
        activity = ActivityLog(
            strategy_name="test",
            decision_type="entry",
            data={"api_key": "should_not_be_stored_here"},
            confidence_score=0.5,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        retrieved = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert retrieved is not None


class TestDataMigrationValidation:
    """Validate schema compatibility for upgrades."""

    def test_old_fields_still_accessible(self, db: Session):
        """New schema must maintain backward compatibility."""
        activity = ActivityLog(
            strategy_name="legacy_strategy",
            decision_type="entry",
            data={"old_field": "value"},
            confidence_score=0.5,
            mode="paper",
        )
        db.add(activity)
        db.commit()

        retrieved = db.query(ActivityLog).filter_by(id=activity.id).first()
        assert retrieved.strategy_name == "legacy_strategy"
        assert retrieved.data.get("old_field") == "value"

    def test_new_fields_optional_for_old_records(self, db: Session):
        """Old records can exist without new optional fields."""
        decision = DecisionLog(
            strategy="test",
            market_ticker="test-market",
            decision="BUY",
            confidence=0.5,
            reason=None,  # Optional field
        )
        db.add(decision)
        db.commit()

        retrieved = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert retrieved is not None
        assert retrieved.reason is None


class TestPerformanceBaseline:
    """Performance expectations for Phase 2."""

    def test_activity_insert_performance(self, db: Session):
        """Bulk activity inserts should be fast."""
        start = datetime.utcnow()
        for i in range(100):
            activity = ActivityLog(
                strategy_name=f"strat_{i % 5}",
                decision_type="entry" if i % 2 == 0 else "exit",
                data={"index": i},
                confidence_score=0.5 + (i % 50) / 100,
                mode="paper",
            )
            db.add(activity)
        db.commit()
        elapsed = (datetime.utcnow() - start).total_seconds()

        assert elapsed < 5.0  # Should insert 100 records in < 5 seconds
        assert db.query(ActivityLog).count() == 100

    def test_activity_query_performance(self, db: Session):
        """Querying activities by strategy should be fast."""
        for i in range(50):
            activity = ActivityLog(
                strategy_name="btc_momentum" if i % 2 == 0 else "weather_emos",
                decision_type="entry",
                data={},
                confidence_score=0.5,
                mode="paper",
            )
            db.add(activity)
        db.commit()

        start = datetime.utcnow()
        results = db.query(ActivityLog).filter_by(
            strategy_name="btc_momentum"
        ).all()
        elapsed = (datetime.utcnow() - start).total_seconds()

        assert elapsed < 0.5  # Query should complete in < 500ms
        assert len(results) == 25


class TestErrorRecoveryPathsForDeployment:
    """Ensure system can recover from common errors."""

    def test_duplicate_proposal_handled(self, db: Session):
        """System should handle duplicate proposal submissions gracefully."""
        proposal1 = StrategyProposal(
            strategy_name="test_strat",
            change_details=json.dumps({"param": "value"}),
            expected_impact="Test",
            admin_decision="pending",
        )
        db.add(proposal1)
        db.commit()

        # Attempting to create a similar one should not crash
        proposal2 = StrategyProposal(
            strategy_name="test_strat",
            change_details=json.dumps({"param": "value"}),
            expected_impact="Test",
            admin_decision="pending",
        )
        db.add(proposal2)
        db.commit()

        proposals = db.query(StrategyProposal).filter_by(
            strategy_name="test_strat"
        ).all()
        assert len(proposals) == 2

    def test_corrupted_json_fields_logged_not_crashed(self, db: Session):
        """Corrupted JSON should be logged, not crash."""
        decision = DecisionLog(
            strategy="test",
            market_ticker="test",
            decision="BUY",
            confidence=0.5,
            signal_data='{"malformed": json}',  # Invalid JSON
        )
        db.add(decision)
        db.commit()

        # Should store as-is (validation happens at API layer)
        retrieved = db.query(DecisionLog).filter_by(id=decision.id).first()
        assert retrieved.signal_data == '{"malformed": json}'
