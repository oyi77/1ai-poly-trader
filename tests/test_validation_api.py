"""Integration tests for API validation error responses."""

import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.api.auth import require_admin

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_admin] = lambda: None
    yield
    app.dependency_overrides.clear()

client = TestClient(app)


class TestSignalValidationAPI:
    """Test signal creation API validation."""
    
    def test_invalid_signal_returns_422(self):
        response = client.post(
            "/api/v1/signals",
            json={
                "market_id": "BTC-5MIN",
                "prediction": 1.5,
                "confidence": 0.8,
                "reasoning": "Test",
                "source": "test"
            }
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
        assert any("prediction" in str(e).lower() for e in error["detail"])
    
    def test_missing_required_field_returns_422(self):
        response = client.post(
            "/api/v1/signals",
            json={
                "market_id": "BTC-5MIN",
                "prediction": 0.65,
                "confidence": 0.8,
                "source": "test"
            }
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
        assert any("reasoning" in str(e).lower() for e in error["detail"])
    
    def test_html_injection_sanitized(self):
        response = client.post(
            "/api/v1/signals",
            json={
                "market_id": "<script>alert('xss')</script>",
                "prediction": 0.65,
                "confidence": 0.8,
                "reasoning": "Test reasoning with <b>HTML</b>",
                "source": "test"
            }
        )
        if response.status_code == 201:
            data = response.json()
            assert "<script>" not in data.get("market_id", "")
            assert "<b>" not in data.get("reasoning", "")


class TestWalletValidationAPI:
    """Test wallet API validation."""
    
    def test_invalid_wallet_address_returns_422(self, monkeypatch):
        monkeypatch.setattr("backend.api.wallets.require_admin", lambda: None)
        
        response = client.post(
            "/api/v1/wallets/config",
            json={
                "address": "invalid_address",
                "pseudonym": "Test Wallet"
            },
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
    
    def test_too_many_tags_returns_422(self, monkeypatch):
        monkeypatch.setattr("backend.api.wallets.require_admin", lambda: None)
        
        response = client.post(
            "/api/v1/wallets/config",
            json={
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
                "tags": [f"tag{i}" for i in range(25)]
            },
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 422


class TestStrategyValidationAPI:
    """Test strategy configuration API validation."""
    
    def test_invalid_interval_returns_422(self, monkeypatch):
        monkeypatch.setattr("backend.api.system.require_admin", lambda: None)
        
        response = client.put(
            "/api/v1/strategies/btc_momentum",
            json={
                "interval_seconds": 5
            },
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
        assert any("interval" in str(e).lower() for e in error["detail"])


class TestBacktestValidationAPI:
    """Test backtest API validation."""
    
    def test_invalid_kelly_fraction_returns_422(self, monkeypatch):
        monkeypatch.setattr("backend.api.backtest.require_admin", lambda: None)
        
        response = client.post(
            "/api/v1/backtest/run",
            json={
                "strategy_name": "btc_momentum",
                "kelly_fraction": 2.0
            },
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error


class TestProposalValidationAPI:
    """Test proposal API validation."""
    
    def test_empty_change_details_returns_422(self):
        response = client.post(
            "/api/v1/proposals",
            json={
                "strategy_name": "btc_momentum",
                "change_details": {},
                "expected_impact": 0.1
            }
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error
    
    def test_impact_out_of_range_returns_422(self):
        response = client.post(
            "/api/v1/proposals",
            json={
                "strategy_name": "btc_momentum",
                "change_details": {"test": "value"},
                "expected_impact": 5.0
            }
        )
        assert response.status_code == 422


class TestValidationErrorMessages:
    """Test that validation errors have clear, actionable messages."""
    
    def test_error_message_includes_field_location(self):
        response = client.post(
            "/api/v1/signals",
            json={
                "market_id": "BTC",
                "prediction": 1.5,
                "confidence": 0.8,
                "reasoning": "Short",
                "source": "test"
            }
        )
        assert response.status_code == 422
        error = response.json()
        
        for detail in error["detail"]:
            assert "loc" in detail
            assert "msg" in detail
            assert "type" in detail
    
    def test_multiple_validation_errors_returned(self):
        response = client.post(
            "/api/v1/signals",
            json={
                "market_id": "BTC",
                "prediction": 1.5,
                "confidence": -0.1,
                "reasoning": "x",
                "source": "test"
            }
        )
        assert response.status_code == 422
        error = response.json()
        assert len(error["detail"]) >= 2
