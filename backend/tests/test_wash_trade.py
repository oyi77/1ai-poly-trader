from backend.core.wash_trade_detector import WashTradeDetector, WashTradeRisk


def _make_trade(maker, taker, price, usd_amount, timestamp):
    return {"maker": maker, "taker": taker, "price": price, "usd_amount": usd_amount, "timestamp": timestamp}


def test_clean_market_low_risk():
    detector = WashTradeDetector()
    trades = [
        _make_trade(f"wallet_maker_{i}", f"wallet_taker_{i}", 0.50 + i * 0.01, 100 + i * 37, 1000 + i * 120)
        for i in range(20)
    ]
    result = detector.analyze_trades(trades, market_id="clean_market")
    assert result.risk == WashTradeRisk.LOW
    assert result.score <= 25


def test_self_trading_detected():
    detector = WashTradeDetector()
    # wallet_A is both maker and taker across different trades
    trades = [
        _make_trade("wallet_A", "wallet_B", 0.50, 500, 1000),
        _make_trade("wallet_C", "wallet_A", 0.50, 500, 1010),
        _make_trade("wallet_D", "wallet_E", 0.51, 300, 1020),
        _make_trade("wallet_F", "wallet_G", 0.52, 200, 1030),
    ]
    result = detector.analyze_trades(trades)
    assert result.indicators["self_trading"] >= 50
    assert result.score > 0


def test_size_uniformity_detected():
    detector = WashTradeDetector()
    # 90% of trades are exactly $100
    trades = [_make_trade(f"m{i}", f"t{i}", 0.50, 100, 1000 + i * 200) for i in range(9)]
    trades.append(_make_trade("mx", "tx", 0.50, 237, 3000))
    result = detector.analyze_trades(trades)
    assert result.indicators["size_uniformity"] == 100.0


def test_timing_clustering_detected():
    detector = WashTradeDetector()
    # 8 trades within 5-second windows out of 9 consecutive pairs (>70%)
    base = 1000
    trades = [_make_trade(f"m{i}", f"t{i}", 0.50 + i * 0.01, 100 + i * 10, base + i * 2) for i in range(9)]
    # add one outlier far away
    trades.append(_make_trade("mx", "tx", 0.60, 200, base + 500))
    result = detector.analyze_trades(trades)
    assert result.indicators["timing_clustering"] >= 50


def test_price_manipulation_detected():
    detector = WashTradeDetector()
    # 80% of trades at price 0.50
    trades = [_make_trade(f"m{i}", f"t{i}", 0.50, 100 + i * 13, 1000 + i * 300) for i in range(8)]
    trades.append(_make_trade("mx", "tx", 0.60, 200, 5000))
    trades.append(_make_trade("my", "ty", 0.70, 150, 6000))
    result = detector.analyze_trades(trades)
    assert result.indicators["price_manipulation"] == 100.0


def test_combined_high_risk():
    detector = WashTradeDetector()
    # Self-trading: wallet_A on both sides
    # Uniform sizes: all $500
    # Same price: all 0.50
    # Tight timing: all within 2 seconds
    trades = [
        _make_trade("wallet_A", "wallet_B", 0.50, 500, 1000),
        _make_trade("wallet_B", "wallet_A", 0.50, 500, 1001),
        _make_trade("wallet_A", "wallet_C", 0.50, 500, 1002),
        _make_trade("wallet_C", "wallet_A", 0.50, 500, 1003),
        _make_trade("wallet_B", "wallet_C", 0.50, 500, 1004),
        _make_trade("wallet_C", "wallet_B", 0.50, 500, 1005),
    ]
    result = detector.analyze_trades(trades)
    assert result.risk == WashTradeRisk.VERY_HIGH
    assert result.score > 75


def test_adjusted_volume():
    detector = WashTradeDetector()
    # score=50 -> 50% reduction
    adjusted = detector.get_adjusted_volume(1000.0, 50)
    assert adjusted == 500.0


def test_adjusted_volume_floor():
    detector = WashTradeDetector()
    # score=95 -> 5% remains, but floor is 10%
    adjusted = detector.get_adjusted_volume(1000.0, 95)
    assert adjusted == 100.0  # floor: 10% of 1000


def test_empty_trades():
    detector = WashTradeDetector()
    result = detector.analyze_trades([])
    assert result.risk == WashTradeRisk.LOW
    assert result.score == 0
    assert all(v == 0.0 for v in result.indicators.values())
