"""
BTC 5-Minute Momentum Strategy (EXPERIMENTAL — DISABLED).

WARNING: This strategy has documented negative live EV: 4W/11L, -49.5% ROI
with technical indicators on binary 5-min markets. Do NOT enable in live mode
without comprehensive re-validation.

This wrapper preserves the existing logic for paper-mode research only.
For production BTC trading, use btc_oracle strategy instead.
"""

import logging

from backend.strategies.base import (
    BaseStrategy,
    StrategyContext,
    CycleResult,
    MarketInfo,
)
from backend.core.decisions import record_decision

logger = logging.getLogger("trading_bot")

EXPERIMENTAL_WARNING = (
    "EXPERIMENTAL — documented -49.5% live ROI on 4W/11L sample. "
    "Do not enable in live mode without re-validation."
)


class BtcMomentumStrategy(BaseStrategy):
    name = "btc_momentum"
    description = f"BTC 5-min momentum (EXPERIMENTAL). {EXPERIMENTAL_WARNING}"
    category = "experimental"
    default_params = {
        "WARNING": EXPERIMENTAL_WARNING,
        "interval_seconds": 60,
        "max_trades_per_scan": 2,
        "max_trade_fraction": 0.03,
    }

    async def market_filter(self, markets: list[MarketInfo]) -> list[MarketInfo]:
        """Filter to BTC 5-min binary markets."""
        return [
            m for m in markets if "btc" in m.slug.lower() and "5m" in m.slug.lower()
        ]

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        result = CycleResult(
            decisions_recorded=0,
            trades_attempted=0,
            trades_placed=0,
        )

        # Log experimental warning on every cycle
        logger.warning(f"BtcMomentumStrategy: {EXPERIMENTAL_WARNING}")

        try:
            # Delegate to existing scan logic
            from backend.core.signals import scan_for_signals

            signals = await scan_for_signals()
            actionable = [s for s in signals if s.passes_threshold]

            params = {**self.default_params, **(ctx.params or {})}
            max_trade_fraction = params.get("max_trade_fraction", 0.03)

            for signal in actionable:
                decision = "BUY" if signal.passes_threshold else "SKIP"
                market_id = getattr(signal.market, "market_id", "unknown")
                record_decision(
                    ctx.db,
                    self.name,
                    market_id,
                    decision,
                    confidence=signal.confidence,
                    signal_data={
                        "direction": signal.direction,
                        "model_probability": signal.model_probability,
                        "market_probability": signal.market_probability,
                        "edge": signal.edge,
                        "btc_price": getattr(signal, "btc_price", None),
                        "experimental_warning": True,
                    },
                    reason=f"btc_momentum edge={signal.edge:.3f} conf={signal.confidence:.2f} [EXPERIMENTAL]",
                )
                result.decisions_recorded += 1
                if decision == "BUY":
                    result.trades_attempted += 1

                    # Compute proper trade size from Kelly or fraction of bankroll
                    bankroll = (
                        ctx.settings.INITIAL_BANKROLL if ctx.mode != "paper" else 100.0
                    )
                    trade_size = (
                        signal.suggested_size
                        if signal.suggested_size > 0
                        else bankroll * max_trade_fraction
                    )
                    trade_size = max(trade_size, 10.0)  # $10 minimum

                    # entry_price: use the token price for the chosen direction
                    if signal.direction == "up":
                        entry_price = getattr(
                            signal.market, "up_price", signal.market_probability
                        )
                    else:
                        entry_price = getattr(
                            signal.market, "down_price", 1.0 - signal.market_probability
                        )

                    result.decisions.append(
                        {
                            "decision": "BUY",
                            "market_ticker": market_id,
                            "direction": signal.direction,
                            "confidence": signal.confidence,
                            "edge": signal.edge,
                            "size": trade_size,
                            "entry_price": entry_price,
                            "suggested_size": trade_size,
                            "model_probability": signal.model_probability,
                            "market_probability": signal.market_probability,
                            "platform": "polymarket",
                            "strategy_name": self.name,
                            "slug": getattr(signal.market, "slug", None),
                            "market_type": "btc",
                        }
                    )

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"BtcMomentumStrategy error: {e}")

        return result
