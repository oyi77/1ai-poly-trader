from backend.core.whale_scoring import calculate_whale_score


def test_empty_trades_returns_zero():
    assert calculate_whale_score([]) == 0.0


def test_all_wins_high_score():
    trades = [{"pnl": 100, "size": 100} for _ in range(10)]
    score = calculate_whale_score(trades, days_active=1.0)
    assert score > 0.5  # high win rate + ROI


def test_all_losses_low_score():
    trades = [{"pnl": -50, "size": 100} for _ in range(10)]
    score = calculate_whale_score(trades, days_active=1.0)
    assert score < 0.3


def test_score_in_range():
    import random

    random.seed(42)
    trades = [{"pnl": random.uniform(-100, 100), "size": 50} for _ in range(20)]
    score = calculate_whale_score(trades)
    assert 0.0 <= score <= 1.0


def test_large_size_boost():
    small = [{"pnl": 10, "size": 100} for _ in range(10)]
    big = [{"pnl": 1000, "size": 10000} for _ in range(10)]
    assert calculate_whale_score(big) > calculate_whale_score(small)
