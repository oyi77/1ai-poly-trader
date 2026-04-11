"""
BTC Oracle Latency Strategy.

Monitors the Chainlink/UMA oracle settlement price vs Polymarket market mid-price
for short-duration BTC binary markets. When the oracle's pre-resolution price
diverges from market mid by > min_edge AND time-to-resolution < max_minutes,
fire a trade.

This strategy exploits the 2-5 second oracle latency window documented in research.
Unlike BTC 5-min momentum (negative EV), this targets a structural market inefficiency.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx

from backend.strategies.base import BaseStrategy, StrategyContext, CycleResult
from backend.core.market_scanner import MarketInfo
from backend.core.decisions import record_decision

logger = logging.getLogger("trading_bot")

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"


async def fetch_btc_price() -> float | None:
    """Fetch current BTC/USD price from CoinGecko (free tier)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                COINGECKO_PRICE_URL,
                params={"ids": "bitcoin", "vs_currencies": "usd"},
            )
            if resp.status_code == 200:
                return float(resp.json()["bitcoin"]["usd"])
    except Exception as e:
        logger.warning(f"BtcOracleStrategy: could not fetch BTC price: {e}")
    return None


def parse_end_date(end_date_str: str | None) -> datetime | None:
    """Parse ISO end_date from Polymarket market metadata."""
    if not end_date_str:
        return None
    try:
        dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def implied_direction(question: str, btc_price: float) -> str | None:
    """
    Infer YES/NO from market question and current price.
    e.g. "Will BTC exceed $95,000 on March 15?" + btc_price=96000 -> "yes"
    Returns "yes", "no", or None if cannot determine.
    """
    import re

    q = question.lower()
    # Extract threshold from question
    match = re.search(r"\$?([\d,]+)", q)
    if not match:
        return None
    threshold = float(match.group(1).replace(",", ""))

    is_above = "above" in q or "exceed" in q or "over" in q or "higher" in q
    is_below = "below" in q or "under" in q or "lower" in q

    if is_above:
        return "yes" if btc_price > threshold else "no"
    if is_below:
        return "yes" if btc_price < threshold else "no"
    return None


class BtcOracleStrategy(BaseStrategy):
    name = "btc_oracle"
    description = (
        "BTC oracle latency arb: exploits 2-5s oracle settlement lag on short-duration BTC markets. "
        "Replaces the negative-EV BTC 5-min momentum strategy."
    )
    category = "arbitrage"
    default_params = {
        "min_edge": 0.03,
        "max_minutes_to_resolution": 10,
        "interval_seconds": 30,
    }

    async def market_filter(self, markets: list[MarketInfo]) -> list[MarketInfo]:
        """Filter to active BTC binary markets resolving within max_minutes."""
        return [
            m
            for m in markets
            if ("btc" in m.slug.lower() or "bitcoin" in m.question.lower())
            and m.end_date is not None
        ]

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        result = CycleResult(decisions_recorded=0, trades_attempted=0, trades_placed=0)
        min_edge = ctx.params.get("min_edge", self.default_params["min_edge"])
        max_minutes = ctx.params.get(
            "max_minutes_to_resolution",
            self.default_params["max_minutes_to_resolution"],
        )

        btc_price = await fetch_btc_price()
        if btc_price is None:
            result.errors.append("Could not fetch BTC price from CoinGecko")
            return result

        # Get candidate markets from MarketWatch (BTC-tagged) or scanner
        from backend.core.market_scanner import fetch_markets_by_keywords

        markets = await fetch_markets_by_keywords(["btc", "bitcoin"], limit=200)
        btc_markets = await self.market_filter(markets)

        now = datetime.now(timezone.utc)

        for market in btc_markets:
            end_dt = parse_end_date(market.end_date)
            if end_dt is None:
                continue
            minutes_remaining = (end_dt - now).total_seconds() / 60.0
            if minutes_remaining < 0 or minutes_remaining > max_minutes:
                continue

            # Determine which direction oracle price implies
            direction = implied_direction(market.question, btc_price)
            if direction is None:
                continue

            market_mid = market.yes_price if direction == "yes" else market.no_price
            # Oracle implies this should resolve YES — if market_mid < (1 - min_edge), there's edge
            oracle_implied = 1.0 if direction == "yes" else 0.0
            edge = abs(oracle_implied - market_mid) - min_edge

            decision = "BUY" if edge > 0 else "SKIP"
            record_decision(
                ctx.db,
                self.name,
                market.ticker,
                decision,
                confidence=min(1.0, max(0.0, edge + min_edge)),
                signal_data={
                    "oracle_price": btc_price,
                    "market_mid": market_mid,
                    "implied_direction": direction,
                    "time_to_resolution_s": minutes_remaining * 60,
                    "edge": edge,
                    "market_question": market.question,
                },
                reason=f"oracle_edge={edge:.3f} btc=${btc_price:,.0f} t={minutes_remaining:.1f}min",
            )
            result.decisions_recorded += 1

            if decision == "BUY":
                result.trades_attempted += 1
                # Populate result.decisions so scan_and_trade_job() / strategy_cycle_job()
                # can feed them into strategy_executor.execute_decisions() for paper + live mode.
                result.decisions.append(
                    {
                        "decision": "BUY",
                        "market_ticker": market.ticker,
                        "direction": direction,
                        "confidence": min(1.0, max(0.0, edge + min_edge)),
                        "edge": edge,
                        "size": ctx.params.get("max_position_usd", 50),
                        "entry_price": market_mid,
                        "suggested_size": ctx.params.get("max_position_usd", 50),
                        "model_probability": 1.0 if direction == "yes" else 0.0,
                        "market_probability": market_mid,
                        "platform": "polymarket",
                        "strategy_name": self.name,
                        "reasoning": f"oracle_edge={edge:.3f} btc=${btc_price:,.0f} t={minutes_remaining:.1f}min",
                        "slug": market.slug,
                    }
                )
                # Also attempt direct CLOB placement for live/testnet mode
                if ctx.clob and ctx.mode != "paper":
                    try:
                        order_result = await ctx.clob.place_limit_order(
                            token_id=market.ticker,
                            side="BUY",
                            price=market_mid,
                            size=ctx.params.get("max_position_usd", 50),
                        )
                        if order_result.success:
                            result.trades_placed += 1
                    except Exception as e:
                        result.errors.append(f"Order failed for {market.ticker}: {e}")

        return result
