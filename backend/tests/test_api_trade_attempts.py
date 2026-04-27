"""Tests for Trade Control Room trade-attempt endpoints."""

from datetime import datetime, timezone

from backend.config import settings


class TestTradeAttemptsApi:
    def setup_method(self):
        settings.ADMIN_API_KEY = None

    def test_trade_attempts_list_returns_items_and_total(self, client, db):
        from backend.models.database import TradeAttempt

        db.add(TradeAttempt(
            attempt_id="attempt-list-1",
            correlation_id="corr-list-1",
            strategy="general_scanner",
            mode="paper",
            market_ticker="LIST-MARKET",
            status="REJECTED",
            phase="risk_gate",
            reason_code="REJECTED_MAX_EXPOSURE",
            reason="max exposure reached",
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

        resp = client.get("/api/v1/trade-attempts?mode=paper")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["market_ticker"] == "LIST-MARKET"
        assert data["items"][0]["reason_code"] == "REJECTED_MAX_EXPOSURE"

    def test_trade_attempts_summary_surfaces_blockers(self, client, db):
        from backend.models.database import TradeAttempt

        db.add_all([
            TradeAttempt(
                attempt_id="attempt-summary-1",
                correlation_id="corr-summary-1",
                strategy="general_scanner",
                mode="live",
                market_ticker="DRAW-MARKET",
                status="REJECTED",
                phase="risk_gate",
                reason_code="REJECTED_DRAWDOWN_BREAKER",
                reason="drawdown breaker",
            ),
            TradeAttempt(
                attempt_id="attempt-summary-2",
                correlation_id="corr-summary-2",
                strategy="general_scanner",
                mode="live",
                market_ticker="WIN-MARKET",
                status="EXECUTED",
                phase="completed",
                reason_code="EXECUTED_TRADE_OPENED",
                reason="Trade opened",
            ),
        ])
        db.commit()

        resp = client.get("/api/v1/trade-attempts/summary?mode=live")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["executed"] == 1
        assert data["blocked"] == 1
        assert data["execution_rate"] == 0.5
        assert data["top_blockers"][0]["reason_code"] == "REJECTED_DRAWDOWN_BREAKER"
        assert data["recent_blockers"][0]["market_ticker"] == "DRAW-MARKET"
