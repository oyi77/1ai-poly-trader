"""Arbitrage opportunity detection across Polymarket markets."""

from dataclasses import dataclass
from typing import List, Optional, Iterable, Dict, Any


@dataclass
class ArbOpportunity:
    market_id: str
    kind: str  # yes_no | cross_market | spread
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    raw_profit: float = 0.0
    net_profit: float = 0.0
    detail: Optional[Dict[str, Any]] = None


class ArbitrageDetector:
    def __init__(self, fee_pct: float = 0.02):
        self.fee_pct = fee_pct

    def detect_yes_no_arb(self, market: Dict[str, Any]) -> Optional[ArbOpportunity]:
        yes = market.get("yes_price")
        no = market.get("no_price")
        if yes is None or no is None:
            return None
        total = yes + no
        if total >= 0.95:
            return None
        raw = 1.0 - total  # synthetic complete-set profit before fees
        net = self.calculate_profit_after_fees(raw)
        if net <= 0:
            return None
        return ArbOpportunity(
            market_id=str(market.get("market_id", "?")),
            kind="yes_no",
            yes_price=yes,
            no_price=no,
            raw_profit=raw,
            net_profit=net,
            detail={"sum": total},
        )

    def detect_cross_market(
        self, market_a: Dict[str, Any], market_b: Dict[str, Any]
    ) -> Optional[ArbOpportunity]:
        if market_a.get("event_id") != market_b.get("event_id"):
            return None
        a_yes = market_a.get("yes_price")
        b_no = market_b.get("no_price")
        if a_yes is None or b_no is None:
            return None
        total = a_yes + b_no
        if total >= 0.99:
            return None
        raw = 1.0 - total
        net = self.calculate_profit_after_fees(raw)
        if net <= 0:
            return None
        return ArbOpportunity(
            market_id=f"{market_a.get('market_id')}+{market_b.get('market_id')}",
            kind="cross_market",
            raw_profit=raw,
            net_profit=net,
            detail={"a": market_a.get("market_id"), "b": market_b.get("market_id")},
        )

    def calculate_profit_after_fees(
        self, raw_profit: float, fee_pct: Optional[float] = None
    ) -> float:
        fee = fee_pct if fee_pct is not None else self.fee_pct
        return round(raw_profit - fee, 6)

    def scan_all(self, markets: Iterable[Dict[str, Any]]) -> List[ArbOpportunity]:
        out: List[ArbOpportunity] = []
        for m in markets:
            op = self.detect_yes_no_arb(m)
            if op:
                out.append(op)
        out.sort(key=lambda o: o.net_profit, reverse=True)
        return out
