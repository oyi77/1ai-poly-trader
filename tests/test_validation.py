"""Tests for API request validation models."""

import pytest
from pydantic import ValidationError

from backend.api.validation import (
    SignalCreateRequest,
    TradeCreateRequest,
    StrategyConfigRequest,
    WalletConfigCreateRequest,
    BacktestRunRequest,
    ProposalCreateRequest,
    CredentialsUpdateRequest,
)


class TestSignalValidation:
    """Test signal creation validation."""
    
    def test_valid_signal(self):
        signal = SignalCreateRequest(
            market_id="BTC-5MIN-UP",
            prediction=0.65,
            confidence=0.8,
            reasoning="Strong momentum indicators with RSI oversold",
            source="btc_momentum",
            weight=1.0
        )
        assert signal.prediction == 0.65
        assert signal.confidence == 0.8
    
    def test_prediction_out_of_range(self):
        with pytest.raises(ValidationError) as exc:
            SignalCreateRequest(
                market_id="BTC-5MIN-UP",
                prediction=1.5,
                confidence=0.8,
                reasoning="Test reasoning",
                source="test",
            )
        assert "prediction" in str(exc.value)
    
    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError) as exc:
            SignalCreateRequest(
                market_id="BTC-5MIN-UP",
                prediction=0.65,
                confidence=-0.1,
                reasoning="Test reasoning",
                source="test",
            )
        assert "confidence" in str(exc.value)
    
    def test_reasoning_too_short(self):
        with pytest.raises(ValidationError) as exc:
            SignalCreateRequest(
                market_id="BTC-5MIN-UP",
                prediction=0.65,
                confidence=0.8,
                reasoning="Short",
                source="test",
            )
        assert "reasoning" in str(exc.value)
    
    def test_html_sanitization(self):
        signal = SignalCreateRequest(
            market_id="<script>alert('xss')</script>",
            prediction=0.65,
            confidence=0.8,
            reasoning="Test <b>bold</b> reasoning",
            source="test<script>",
        )
        assert "<script>" not in signal.market_id
        assert "<b>" not in signal.reasoning
        assert "<script>" not in signal.source


class TestTradeValidation:
    """Test trade creation validation."""
    
    def test_valid_trade(self):
        trade = TradeCreateRequest(
            market_ticker="BTC-5MIN-UP",
            direction="YES",
            amount=100.0,
            price=0.55,
        )
        assert trade.amount == 100.0
        assert trade.price == 0.55
    
    def test_negative_amount(self):
        with pytest.raises(ValidationError) as exc:
            TradeCreateRequest(
                market_ticker="BTC-5MIN-UP",
                direction="YES",
                amount=-50.0,
            )
        assert "amount" in str(exc.value)
    
    def test_amount_too_large(self):
        with pytest.raises(ValidationError) as exc:
            TradeCreateRequest(
                market_ticker="BTC-5MIN-UP",
                direction="YES",
                amount=2000000.0,
            )
        assert "amount" in str(exc.value)
    
    def test_price_out_of_range(self):
        with pytest.raises(ValidationError) as exc:
            TradeCreateRequest(
                market_ticker="BTC-5MIN-UP",
                direction="YES",
                amount=100.0,
                price=1.5,
            )
        assert "price" in str(exc.value)


class TestStrategyConfigValidation:
    """Test strategy configuration validation."""
    
    def test_valid_config(self):
        config = StrategyConfigRequest(
            enabled=True,
            interval_seconds=60,
            params={"min_edge": 0.05, "max_position": 1000}
        )
        assert config.enabled is True
        assert config.interval_seconds == 60
    
    def test_interval_too_short(self):
        with pytest.raises(ValidationError) as exc:
            StrategyConfigRequest(interval_seconds=5)
        assert "interval_seconds" in str(exc.value)
    
    def test_interval_too_long(self):
        with pytest.raises(ValidationError) as exc:
            StrategyConfigRequest(interval_seconds=100000)
        assert "interval_seconds" in str(exc.value)
    
    def test_nested_params_depth_limit(self):
        deeply_nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "too deep"}}}}}}}
        with pytest.raises(ValidationError) as exc:
            StrategyConfigRequest(params=deeply_nested)
        assert "nesting too deep" in str(exc.value).lower()


class TestWalletValidation:
    """Test wallet configuration validation."""
    
    def test_valid_wallet(self):
        wallet = WalletConfigCreateRequest(
            address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            pseudonym="Main Wallet",
            tags=["trading", "primary"]
        )
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42
    
    def test_invalid_address_format(self):
        with pytest.raises(ValidationError) as exc:
            WalletConfigCreateRequest(address="invalid_address")
        assert "address" in str(exc.value).lower()
    
    def test_too_many_tags(self):
        with pytest.raises(ValidationError) as exc:
            WalletConfigCreateRequest(
                address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
                tags=[f"tag{i}" for i in range(25)]
            )
        assert "tags" in str(exc.value).lower()


class TestBacktestValidation:
    """Test backtest request validation."""
    
    def test_valid_backtest(self):
        backtest = BacktestRunRequest(
            strategy_name="btc_momentum",
            initial_bankroll=10000.0,
            kelly_fraction=0.25,
        )
        assert backtest.initial_bankroll == 10000.0
        assert backtest.kelly_fraction == 0.25
    
    def test_kelly_fraction_out_of_range(self):
        with pytest.raises(ValidationError) as exc:
            BacktestRunRequest(
                strategy_name="test",
                kelly_fraction=1.5
            )
        assert "kelly_fraction" in str(exc.value)
    
    def test_invalid_date_format(self):
        with pytest.raises(ValidationError) as exc:
            BacktestRunRequest(
                strategy_name="test",
                start_date="not-a-date"
            )
        assert "date" in str(exc.value).lower()


class TestProposalValidation:
    """Test proposal creation validation."""
    
    def test_valid_proposal(self):
        proposal = ProposalCreateRequest(
            strategy_name="btc_momentum",
            change_details={"min_edge": 0.03, "enabled": True},
            expected_impact=0.15
        )
        assert proposal.expected_impact == 0.15
    
    def test_empty_change_details(self):
        with pytest.raises(ValidationError) as exc:
            ProposalCreateRequest(
                strategy_name="test",
                change_details={},
                expected_impact=0.1
            )
        assert "change_details" in str(exc.value).lower()
    
    def test_impact_out_of_range(self):
        with pytest.raises(ValidationError) as exc:
            ProposalCreateRequest(
                strategy_name="test",
                change_details={"test": "value"},
                expected_impact=2.0
            )
        assert "expected_impact" in str(exc.value)


class TestCredentialsValidation:
    """Test credentials update validation."""
    
    def test_valid_private_key(self):
        creds = CredentialsUpdateRequest(
            private_key="0x" + "a" * 64
        )
        assert creds.private_key.startswith("0x")
        assert len(creds.private_key) == 66
    
    def test_private_key_without_prefix(self):
        creds = CredentialsUpdateRequest(
            private_key="a" * 64
        )
        assert creds.private_key.startswith("0x")
    
    def test_invalid_private_key(self):
        with pytest.raises(ValidationError) as exc:
            CredentialsUpdateRequest(private_key="invalid")
        assert "private_key" in str(exc.value).lower()
    
    def test_at_least_one_field_required(self):
        with pytest.raises(ValidationError) as exc:
            CredentialsUpdateRequest()
        assert "at least one" in str(exc.value).lower()
