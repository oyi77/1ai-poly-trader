"""Integration tests for /api/dashboard, /api/stats, and /api/signals endpoints.

Uses the shared conftest.py fixtures (client, db) backed by in-memory SQLite.
External API calls (microstructure, BTC markets, signals) are mocked so tests
run fast and deterministically.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_micro():
    micro = MagicMock()
    micro.rsi = 50.0
    micro.momentum_1m = 0.0
    micro.momentum_5m = 0.0
    micro.momentum_15m = 0.0
    micro.vwap_deviation = 0.0
    micro.sma_crossover = 0.0
    micro.volatility = 0.02
    micro.price = 65000.0
    micro.source = "binance"
    return micro


def _mock_btc_price():
    price = MagicMock()
    price.current_price = 65000.0
    price.change_24h = 1.5
    price.change_7d = 3.0
    price.market_cap = 1_200_000_000_000.0
    price.volume_24h = 40_000_000_000.0
    from datetime import datetime
    price.last_updated = datetime.utcnow()
    return price


# ---------------------------------------------------------------------------
# /api/stats
# ---------------------------------------------------------------------------


class TestStatsEndpoint:
    def test_stats_returns_200(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_stats_has_expected_keys(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        required_keys = {
            "bankroll",
            "total_trades",
            "winning_trades",
            "win_rate",
            "total_pnl",
            "is_running",
        }
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_stats_bankroll_is_numeric(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert isinstance(data["bankroll"], (int, float))
        assert data["bankroll"] >= 0

    def test_stats_total_trades_is_int(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert isinstance(data["total_trades"], int)

    def test_stats_win_rate_in_range(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert 0.0 <= data["win_rate"] <= 1.0

    def test_stats_has_paper_and_live_dicts(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert "paper" in data
        assert "live" in data
        assert isinstance(data["paper"], dict)
        assert isinstance(data["live"], dict)


# ---------------------------------------------------------------------------
# /api/dashboard
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:
    def _get_dashboard(self, client):
        """Call dashboard with mocked external services."""
        with patch(
            "backend.api.main.compute_btc_microstructure",
            AsyncMock(return_value=_mock_micro()),
        ), patch(
            "backend.api.main.fetch_crypto_price",
            AsyncMock(return_value=_mock_btc_price()),
        ), patch(
            "backend.api.main.fetch_active_btc_markets",
            AsyncMock(return_value=[]),
        ), patch(
            "backend.api.main.scan_for_signals",
            AsyncMock(return_value=[]),
        ):
            return client.get("/api/dashboard")

    def test_dashboard_returns_200(self, client):
        resp = self._get_dashboard(client)
        assert resp.status_code == 200

    def test_dashboard_returns_valid_structure(self, client):
        """Dashboard response must contain all top-level keys."""
        resp = self._get_dashboard(client)
        data = resp.json()
        required_keys = {
            "stats",
            "windows",
            "active_signals",
            "recent_trades",
            "equity_curve",
            "trading_mode",
        }
        for key in required_keys:
            assert key in data, f"Missing key in dashboard response: {key}"

    def test_dashboard_stats_is_dict(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["stats"], dict)

    def test_dashboard_recent_trades_is_list(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["recent_trades"], list)

    def test_dashboard_active_signals_is_list(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["active_signals"], list)

    def test_dashboard_windows_is_list(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["windows"], list)

    def test_dashboard_equity_curve_is_list(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["equity_curve"], list)

    def test_dashboard_trading_mode_is_string(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data["trading_mode"], str)
        assert data["trading_mode"] in ("paper", "testnet", "live")

    def test_dashboard_stats_has_bankroll(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert "bankroll" in data["stats"]
        assert isinstance(data["stats"]["bankroll"], (int, float))

    def test_dashboard_weather_signals_is_list(self, client):
        resp = self._get_dashboard(client)
        data = resp.json()
        assert isinstance(data.get("weather_signals", []), list)


# ---------------------------------------------------------------------------
# /api/signals — via trading router
# ---------------------------------------------------------------------------


class TestSignalsEndpoint:
    def test_signals_endpoint_returns_200(self, client):
        with patch(
            "backend.core.signals.compute_btc_microstructure",
            AsyncMock(return_value=_mock_micro()),
        ), patch(
            "backend.core.signals.fetch_active_btc_markets",
            AsyncMock(return_value=[]),
        ):
            resp = client.get("/api/signals")
        assert resp.status_code == 200

    def test_signals_returns_list(self, client):
        with patch(
            "backend.core.signals.compute_btc_microstructure",
            AsyncMock(return_value=_mock_micro()),
        ), patch(
            "backend.core.signals.fetch_active_btc_markets",
            AsyncMock(return_value=[]),
        ):
            resp = client.get("/api/signals")
        data = resp.json()
        assert isinstance(data, list)

    def test_signals_empty_when_no_markets(self, client):
        """With no BTC markets available, signals list is empty."""
        with patch(
            "backend.core.signals.fetch_active_btc_markets",
            AsyncMock(return_value=[]),
        ), patch(
            "backend.core.signals.compute_btc_microstructure",
            AsyncMock(return_value=_mock_micro()),
        ):
            resp = client.get("/api/signals")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /api/health — smoke test (already covered in test_api_health.py)
# ---------------------------------------------------------------------------


class TestHealthSmoke:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
