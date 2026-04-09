"""
Tests for order book engine: LiveOrderBook, OrderBookAnalyzer, slippage calculator.

WebSocket connection is not tested here — only data structures and calculations.
"""
import pytest

from backend.data.orderbook_ws import LiveOrderBook
from backend.core.orderbook_analyzer import OrderBookAnalyzer
from backend.core.slippage import calculate_slippage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_book(
    bids: list | None = None,
    asks: list | None = None,
    token_id: str = "TEST",
) -> LiveOrderBook:
    """Create a LiveOrderBook pre-populated with given levels."""
    book = LiveOrderBook(token_id=token_id)
    book.apply_snapshot(
        bids=bids or [],
        asks=asks or [],
    )
    return book


# ---------------------------------------------------------------------------
# 1. mid_price
# ---------------------------------------------------------------------------

def test_live_order_book_mid_price():
    book = _make_book(bids=[[0.40, 100]], asks=[[0.60, 100]])
    assert book.mid_price == pytest.approx(0.50)


def test_live_order_book_mid_price_single_side():
    book = _make_book(bids=[[0.45, 50]])
    assert book.mid_price == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# 2. spread
# ---------------------------------------------------------------------------

def test_live_order_book_spread():
    book = _make_book(bids=[[0.40, 100]], asks=[[0.60, 100]])
    assert book.spread == pytest.approx(0.20)
    assert book.spread_pct == pytest.approx(0.20 / 0.50)


# ---------------------------------------------------------------------------
# 3. imbalance
# ---------------------------------------------------------------------------

def test_live_order_book_imbalance():
    # Equal bid/ask depth → imbalance = 0
    book = _make_book(bids=[[0.40, 100]], asks=[[0.60, 100]])
    assert book.imbalance == pytest.approx(0.0)

    # Only bids → imbalance = 1
    book_bids_only = _make_book(bids=[[0.40, 200]])
    assert book_bids_only.imbalance == pytest.approx(1.0)

    # Only asks → imbalance = -1
    book_asks_only = _make_book(asks=[[0.60, 200]])
    assert book_asks_only.imbalance == pytest.approx(-1.0)

    # Imbalance in range [-1, 1]
    book_skewed = _make_book(bids=[[0.40, 300]], asks=[[0.60, 100]])
    assert -1.0 <= book_skewed.imbalance <= 1.0
    assert book_skewed.imbalance > 0  # more bids


# ---------------------------------------------------------------------------
# 4. apply_delta — add new level
# ---------------------------------------------------------------------------

def test_apply_delta_add_level():
    book = _make_book(bids=[[0.40, 100]], asks=[[0.60, 100]])
    book.apply_delta("BID", 0.38, 50)
    prices = [level[0] for level in book.bids]
    assert 0.38 in prices
    # bids should remain sorted descending
    assert prices == sorted(prices, reverse=True)


# ---------------------------------------------------------------------------
# 5. apply_delta — remove level (size=0)
# ---------------------------------------------------------------------------

def test_apply_delta_remove_level():
    book = _make_book(bids=[[0.40, 100], [0.38, 50]], asks=[[0.60, 100]])
    book.apply_delta("BID", 0.40, 0)
    prices = [level[0] for level in book.bids]
    assert 0.40 not in prices
    assert 0.38 in prices


# ---------------------------------------------------------------------------
# 6. apply_snapshot — full book replacement
# ---------------------------------------------------------------------------

def test_apply_snapshot():
    book = _make_book(bids=[[0.30, 999]], asks=[[0.70, 999]])
    book.apply_snapshot(
        bids=[[0.45, 200], [0.43, 100]],
        asks=[[0.55, 150], [0.57, 80]],
    )
    assert book.bids[0][0] == pytest.approx(0.45)  # best bid first
    assert book.asks[0][0] == pytest.approx(0.55)  # best ask first
    assert len(book.bids) == 2
    assert len(book.asks) == 2


# ---------------------------------------------------------------------------
# 7. slippage — small order fits in first level
# ---------------------------------------------------------------------------

def test_slippage_small_order():
    book = _make_book(
        bids=[[0.49, 1000]],
        asks=[[0.51, 1000]],
    )
    est = calculate_slippage(book, "BUY", 10)
    assert est.fully_filled is True
    assert est.levels_consumed == 1
    assert est.execution_price == pytest.approx(0.51)
    assert est.filled_amount == pytest.approx(10)
    # slippage from mid (0.50) should be small and positive for a buy
    assert est.slippage > 0


# ---------------------------------------------------------------------------
# 8. slippage — large order walks multiple levels
# ---------------------------------------------------------------------------

def test_slippage_large_order():
    book = _make_book(
        bids=[[0.49, 100], [0.48, 100], [0.47, 100]],
        asks=[[0.51, 50], [0.52, 50], [0.53, 50]],
    )
    est = calculate_slippage(book, "BUY", 120)
    assert est.fully_filled is True
    assert est.levels_consumed >= 2
    # VWAP should be above best ask since we walked into deeper levels
    assert est.execution_price > 0.51


# ---------------------------------------------------------------------------
# 9. slippage — insufficient liquidity (not fully filled)
# ---------------------------------------------------------------------------

def test_slippage_insufficient_liquidity():
    book = _make_book(
        bids=[[0.49, 10]],
        asks=[[0.51, 10]],
    )
    est = calculate_slippage(book, "BUY", 100)
    assert est.fully_filled is False
    assert est.filled_amount == pytest.approx(10)
    assert est.levels_consumed == 1


# ---------------------------------------------------------------------------
# 10. analyzer — support and resistance detection
# ---------------------------------------------------------------------------

def test_analyzer_support_resistance():
    # One dominant bid level (size >> average) and one large ask level
    book = _make_book(
        bids=[[0.48, 10], [0.47, 10], [0.45, 500]],   # 0.45 is a support
        asks=[[0.52, 10], [0.53, 10], [0.55, 500]],   # 0.55 is resistance
    )
    analyzer = OrderBookAnalyzer()
    analysis = analyzer.analyze(book)

    assert 0.45 in analysis.support_levels
    assert 0.55 in analysis.resistance_levels

    # The large levels should also appear in large_bids / large_asks (5x avg)
    avg_bid = book.bid_depth / len(book.bids)  # (10+10+500)/3 ≈ 173
    if 500 > 5 * avg_bid:
        assert any(lb["price"] == 0.45 for lb in analysis.large_bids)


# ---------------------------------------------------------------------------
# 11. analyzer — warnings
# ---------------------------------------------------------------------------

def test_analyzer_warnings_thin_liquidity():
    book = _make_book(bids=[[0.49, 1]], asks=[[0.51, 1]])
    analyzer = OrderBookAnalyzer()
    analysis = analyzer.analyze(book)
    assert "thin_liquidity" in analysis.warnings


def test_analyzer_warnings_wide_spread():
    book = _make_book(
        bids=[[0.30, 10000]],
        asks=[[0.70, 10000]],
    )
    analyzer = OrderBookAnalyzer()
    analysis = analyzer.analyze(book)
    assert "wide_spread" in analysis.warnings
