"""
Order book analysis engine for PolyEdge.

Analyses a LiveOrderBook to extract support/resistance levels,
detect large (iceberg) orders, and emit warnings about thin liquidity
or wide spreads.
"""
from dataclasses import dataclass, field

from backend.data.orderbook_ws import LiveOrderBook


@dataclass
class OrderBookAnalysis:
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float
    mid_price: float
    bid_depth: float
    ask_depth: float
    imbalance: float  # -1 to 1 (positive = more bids)
    support_levels: list = field(default_factory=list)    # significant bid prices
    resistance_levels: list = field(default_factory=list)  # significant ask prices
    large_bids: list = field(default_factory=list)  # [{price, size}] iceberg detection
    large_asks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class OrderBookAnalyzer:
    """Stateless analyser — call analyze() each time you need a fresh snapshot."""

    def analyze(self, book: LiveOrderBook) -> OrderBookAnalysis:
        """Compute a full analysis from the current order book state."""
        best_bid = book.bids[0][0] if book.bids else 0.0
        best_ask = book.asks[0][0] if book.asks else 0.0

        # --- bid support / resistance ---
        avg_bid_size = (book.bid_depth / len(book.bids)) if book.bids else 0.0
        avg_ask_size = (book.ask_depth / len(book.asks)) if book.asks else 0.0

        support_levels = [
            level[0]
            for level in book.bids
            if avg_bid_size > 0 and level[1] > 2 * avg_bid_size
        ]

        resistance_levels = [
            level[0]
            for level in book.asks
            if avg_ask_size > 0 and level[1] > 2 * avg_ask_size
        ]

        # --- large (iceberg) orders: size > 5x average ---
        large_bids = [
            {"price": level[0], "size": level[1]}
            for level in book.bids
            if avg_bid_size > 0 and level[1] > 5 * avg_bid_size
        ]

        large_asks = [
            {"price": level[0], "size": level[1]}
            for level in book.asks
            if avg_ask_size > 0 and level[1] > 5 * avg_ask_size
        ]

        # --- warnings ---
        warnings: list[str] = []
        total_depth = book.bid_depth + book.ask_depth
        if total_depth < 1000:
            warnings.append("thin_liquidity")
        if book.spread_pct > 0.05:
            warnings.append("wide_spread")

        return OrderBookAnalysis(
            best_bid=best_bid,
            best_ask=best_ask,
            spread=book.spread,
            spread_pct=book.spread_pct,
            mid_price=book.mid_price,
            bid_depth=book.bid_depth,
            ask_depth=book.ask_depth,
            imbalance=book.imbalance,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            large_bids=large_bids,
            large_asks=large_asks,
            warnings=warnings,
        )
