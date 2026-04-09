"""Tests for backend/ai/ensemble.py — multi-model signal ensemble."""
import pytest

from backend.ai.ensemble import EnsembleSignal, EnsembleSignalGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gen():
    return EnsembleSignalGenerator()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_combine_all_components(gen):
    """All signals provided; combined probability is a weighted sum of components."""
    result = gen.combine_signals(
        technical_prob=0.7,
        ai_prob=0.6,
        orderbook_imbalance=0.5,
        wash_trade_score=0,
        market_price=0.5,
    )
    assert isinstance(result, EnsembleSignal)
    assert 0.01 <= result.combined_probability <= 0.99
    assert 0.0 <= result.confidence <= 1.0

    # Manually compute expected: 0.4*0.7 + 0.3*0.6 + 0.15*(0.5+0.5*0.15)
    # orderbook_prob = 0.5 + 0.5*0.15 = 0.575
    # combined = 0.4*0.7 + 0.3*0.6 + 0.15*0.575 = 0.28 + 0.18 + 0.08625 = 0.54625
    assert abs(result.combined_probability - 0.54625) < 1e-6

    # All four keys present in breakdown
    assert "technical" in result.component_breakdown
    assert "ai" in result.component_breakdown
    assert "orderbook" in result.component_breakdown
    assert "data_quality" in result.component_breakdown


def test_combine_without_ai(gen):
    """When ai_prob is None, AI weight is redistributed to technical."""
    result_no_ai = gen.combine_signals(
        technical_prob=0.7,
        ai_prob=None,
        orderbook_imbalance=0.0,
        wash_trade_score=0,
        market_price=0.5,
    )
    # With ai_prob=None: technical weight = 0.40 + 0.30 = 0.70
    # orderbook_prob = 0.5 + 0.0*0.15 = 0.5
    # combined = 0.70*0.7 + 0.15*0.5 = 0.49 + 0.075 = 0.565
    assert abs(result_no_ai.combined_probability - 0.565) < 1e-6

    # "ai" key should not be in breakdown (weight is 0, not added)
    assert "ai" not in result_no_ai.component_breakdown

    # Providing ai_prob should give a different result
    result_with_ai = gen.combine_signals(
        technical_prob=0.7,
        ai_prob=0.5,
        orderbook_imbalance=0.0,
        wash_trade_score=0,
        market_price=0.5,
    )
    assert result_no_ai.combined_probability != result_with_ai.combined_probability


def test_edge_calculation(gen):
    """Edge equals |combined_probability - market_price|."""
    market_price = 0.4
    result = gen.combine_signals(
        technical_prob=0.6,
        ai_prob=0.65,
        orderbook_imbalance=0.2,
        wash_trade_score=10,
        market_price=market_price,
    )
    assert abs(result.edge - abs(result.combined_probability - market_price)) < 1e-9


def test_clamp_probability(gen):
    """Extreme inputs must not produce a probability outside [0.01, 0.99]."""
    # Push toward 0
    low = gen.combine_signals(
        technical_prob=0.0,
        ai_prob=0.0,
        orderbook_imbalance=-1.0,
        wash_trade_score=100,
        market_price=0.5,
    )
    assert low.combined_probability >= 0.01

    # Push toward 1
    high = gen.combine_signals(
        technical_prob=1.0,
        ai_prob=1.0,
        orderbook_imbalance=1.0,
        wash_trade_score=0,
        market_price=0.5,
    )
    assert high.combined_probability <= 0.99


def test_wash_trade_reduces_confidence(gen):
    """Higher wash_trade_score should reduce confidence."""
    clean = gen.combine_signals(
        technical_prob=0.6,
        ai_prob=0.6,
        orderbook_imbalance=0.0,
        wash_trade_score=0,
        market_price=0.5,
    )
    dirty = gen.combine_signals(
        technical_prob=0.6,
        ai_prob=0.6,
        orderbook_imbalance=0.0,
        wash_trade_score=80,
        market_price=0.5,
    )
    assert dirty.confidence < clean.confidence
