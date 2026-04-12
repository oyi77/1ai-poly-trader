"""Order execution module for CopyTrader.

Handles leaderboard scoring, trader selection, and order mirroring logic.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from backend.strategies.wallet_sync import WalletTrade

logger = logging.getLogger("trading_bot")

DATA_HOST = "https://data-api.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"

# Minimum trade size (USDC) from whale to indicate conviction
MIN_WHALE_TRADE_SIZE = 50.0

# Minimum days until resolution to copy a trade
MIN_DAYS_TO_RESOLUTION = 7

# BTC 5-min market slug pattern to skip
BTC_5M_SLUG_PATTERN = "btc-updown-5m"


@dataclass
class ScoredTrader:
    """Represents a scored trader from the leaderboard."""

    wallet: str
    pseudonym: str
    profit_30d: float
    win_rate: float
    total_trades: int
    unique_markets: int
    estimated_bankroll: (
        float  # sum of open positions + recent pnl — manual override via config
    )
    score: float = 0.0

    @property
    def market_diversity(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return min(1.0, self.unique_markets / self.total_trades)


@dataclass
class CopySignal:
    """Represents a copy trading signal."""

    source_wallet: str
    source_trade: WalletTrade
    our_side: str
    our_outcome: str
    our_size: float  # Kelly-proportioned USDC size
    market_price: float
    trader_score: float
    reasoning: str
    timestamp: any  # datetime from datetime.now(timezone.utc)


class LeaderboardScorer:
    """Fetches and scores Polymarket leaderboard traders."""

    WEIGHTS = {
        "profit_30d": 0.35,
        "win_rate": 0.25,
        "market_diversity": 0.20,
        "consistency": 0.20,
    }

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def _fetch_actual_bankroll(self, wallet: str) -> Optional[float]:
        try:
            resp = await self._http.get(
                f"{DATA_HOST}/positions",
                params={"user": wallet},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            positions = resp.json()
            if not positions:
                return None

            total_value = 0.0
            for pos in positions:
                value = pos.get("assetValue") or pos.get("value") or pos.get("size")
                if value:
                    try:
                        total_value += abs(float(value))
                    except (ValueError, TypeError):
                        pass

            realized_pnl = 0.0
            if positions and len(positions) > 0:
                for pos in positions:
                    pnl = (
                        pos.get("realizedPnl")
                        or pos.get("realizedPnl24h")
                        or pos.get("pnl")
                    )
                    if pnl:
                        try:
                            realized_pnl += float(pnl)
                        except (ValueError, TypeError):
                            pass

            return total_value + realized_pnl if total_value > 0 else None
        except (httpx.HTTPError, Exception) as e:
            logger.debug(
                f"[order_executor._fetch_actual_bankroll] {type(e).__name__}: Failed to fetch positions for {wallet[:10]}...: {e}"
            )
            return None

    async def fetch_and_score(self, top_n: int = 50) -> list[ScoredTrader]:
        entries = []
        # Try data-api leaderboard first
        try:
            resp = await self._http.get(
                f"{DATA_HOST}/leaderboard", params={"window": "30d"}
            )
            resp.raise_for_status()
            entries = resp.json()
        except (httpx.HTTPError, Exception) as e:
            logger.warning(
                f"[order_executor.fetch_and_score] Leaderboard data-api unavailable ({type(e).__name__}), trying scraper fallback"
            )
            # Fallback: try the polymarket_scraper
            try:
                from backend.data.polymarket_scraper import fetch_real_leaderboard

                scraped = await fetch_real_leaderboard(limit=top_n)
                if scraped:
                    # Normalize scraped entries to match expected format
                    entries = [
                        {
                            "proxyWallet": t.get("wallet", t.get("address", "")),
                            "name": t.get(
                                "pseudonym", t.get("name", t.get("username", "unknown"))
                            ),
                            "profit": t.get(
                                "profit_30d", t.get("profit_loss", t.get("pnl", 0))
                            ),
                            "pnlPercentage": t.get("win_rate", 0) * 100,
                            "tradesCount": t.get(
                                "total_trades",
                                t.get("positions_count", t.get("trades", 0)),
                            ),
                            "marketsTraded": t.get(
                                "unique_markets", t.get("markets_traded", 0)
                            ),
                        }
                        for t in scraped
                    ]
                    logger.info(
                        f"[order_executor] Scraper fallback returned {len(entries)} traders"
                    )
            except Exception as scrape_err:
                logger.warning(
                    f"[order_executor] {type(scrape_err).__name__}: Scraper fallback also failed: {scrape_err}"
                )

        if not entries:
            return []

        profits = [float(e.get("profit", 0)) for e in entries]

        max_profit = max(profits) if profits else 1.0
        max_profit = max_profit if max_profit > 0 else 1.0

        traders = []
        for e in entries[:top_n]:
            profit = float(e.get("profit", 0))
            win_rate = float(e.get("pnlPercentage", 0)) / 100
            trades = int(e.get("tradesCount", 0))

            wallet = e.get("proxyWallet", e.get("address", ""))

            actual_bankroll = await self._fetch_actual_bankroll(wallet)
            if actual_bankroll and actual_bankroll >= 100:
                est_bankroll = actual_bankroll
            else:
                est_bankroll = max(abs(profit) * 5, 1000.0)

            trader = ScoredTrader(
                wallet=e.get("proxyWallet", e.get("address", "")),
                pseudonym=e.get("name", e.get("pseudonym", "unknown")),
                profit_30d=profit,
                win_rate=max(0.0, min(1.0, win_rate)),
                total_trades=trades,
                unique_markets=int(
                    e.get("marketsTraded", trades)
                ),  # fallback to trades
                estimated_bankroll=est_bankroll,
            )

            # Composite score (0–100)
            profit_score = min(1.0, profit / max_profit) if max_profit > 0 else 0.0
            win_rate_score = trader.win_rate
            diversity_score = trader.market_diversity
            # Consistency: prefer traders with similar-sized bets (low variance in size)
            # We don't have per-trade sizes from leaderboard, so use proxy:
            # higher trade count with consistent profit = more consistent
            consistency_score = min(1.0, trades / 100) * win_rate_score

            trader.score = 100 * (
                self.WEIGHTS["profit_30d"] * profit_score
                + self.WEIGHTS["win_rate"] * win_rate_score
                + self.WEIGHTS["market_diversity"] * diversity_score
                + self.WEIGHTS["consistency"] * consistency_score
            )

            traders.append(trader)

        traders.sort(key=lambda t: t.score, reverse=True)
        logger.info(
            f"Scored {len(traders)} traders. Top: {traders[0].pseudonym} score={traders[0].score:.1f}"
        )
        return traders


class OrderExecutor:
    """Handles order mirroring logic for copy trading."""

    def __init__(
        self, bankroll: float = 1000.0, http: Optional[httpx.AsyncClient] = None
    ):
        self.bankroll = bankroll
        self._http = http
        # Cache: condition_id -> (slug, end_date_iso) or None
        self._market_cache: dict[str, Optional[tuple[str, str]]] = {}

    async def _fetch_market_meta(self, condition_id: str) -> Optional[tuple[str, str]]:
        """Fetch (slug, end_date_iso) for a market from Gamma API. Returns None on failure."""
        if condition_id in self._market_cache:
            return self._market_cache[condition_id]

        if not self._http:
            return None

        try:
            resp = await self._http.get(
                f"{GAMMA_HOST}/markets",
                params={"conditionId": condition_id},
                timeout=10.0,
            )
            if resp.status_code != 200:
                self._market_cache[condition_id] = None
                return None
            data = resp.json()
            markets = data if isinstance(data, list) else data.get("markets", [data])
            if not markets:
                self._market_cache[condition_id] = None
                return None
            m = markets[0]
            slug = m.get("slug", "")
            end_date = m.get("endDate") or m.get("end_date") or m.get("endDateIso", "")
            result = (slug, end_date) if end_date else (slug, "")
            self._market_cache[condition_id] = result
            return result
        except (httpx.HTTPError, Exception) as e:
            logger.debug(
                f"[order_executor._fetch_market_meta] {type(e).__name__}: Market meta fetch failed for {condition_id[:12]}: {e}"
            )
            self._market_cache[condition_id] = None
            return None

    async def mirror_buy_async(
        self, trader: ScoredTrader, trade: WalletTrade
    ) -> Optional[CopySignal]:
        """Async version of mirror_buy with market resolution lookups."""
        # Filter 1: minimum whale trade size (conviction filter)
        if trade.size < MIN_WHALE_TRADE_SIZE:
            logger.debug(
                f"Skipping copy: trade size ${trade.size:.2f} < ${MIN_WHALE_TRADE_SIZE} min | {trade.title[:40]}"
            )
            return None

        # Filter 2: fetch market metadata for slug and end_date checks
        meta = await self._fetch_market_meta(trade.condition_id)
        if meta:
            slug, end_date_iso = meta

            # Filter 3: skip BTC 5-min markets
            if BTC_5M_SLUG_PATTERN in slug:
                logger.debug(f"Skipping copy: BTC 5-min market slug={slug}")
                return None

            # Filter 4: only copy markets with resolution > 7 days away
            if end_date_iso:
                try:
                    end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                    days_remaining = (end_dt - datetime.now(timezone.utc)).days
                    if days_remaining < MIN_DAYS_TO_RESOLUTION:
                        logger.debug(
                            f"Skipping copy: only {days_remaining}d to resolution (need {MIN_DAYS_TO_RESOLUTION}d) | {trade.title[:40]}"
                        )
                        return None
                except ValueError as e:
                    logger.debug(
                        f"[order_executor.mirror_buy_async] {type(e).__name__}: Could not parse end_date '{end_date_iso}': {e}"
                    )

        return self.mirror_buy(trader, trade)

    def mirror_buy(
        self, trader: ScoredTrader, trade: WalletTrade
    ) -> Optional[CopySignal]:
        """Create a proportional buy signal from a trader's buy trade."""
        if trader.estimated_bankroll <= 0:
            return None

        # Filter: minimum whale trade size (conviction filter)
        if trade.size < MIN_WHALE_TRADE_SIZE:
            logger.debug(
                f"Skipping copy: trade size ${trade.size:.2f} < ${MIN_WHALE_TRADE_SIZE} min | {trade.title[:40]}"
            )
            return None

        # Filter: skip BTC 5-min markets by title heuristic (slug not available here)
        if BTC_5M_SLUG_PATTERN in (trade.title or "").lower():
            logger.debug(
                f"Skipping copy: BTC 5-min market in title | {trade.title[:40]}"
            )
            return None

        # Proportional sizing: (their trade size / their bankroll) * our bankroll
        their_pct = trade.size / trader.estimated_bankroll
        our_size = their_pct * self.bankroll

        # Cap at 5% of our bankroll
        our_size = min(our_size, 0.05 * self.bankroll)
        our_size = max(0.0, our_size)

        if our_size < 1.0:  # Below Polymarket minimum
            return None

        reasoning = (
            f"Copying {trader.pseudonym} (score={trader.score:.0f}) | "
            f"BUY {trade.outcome} @ {trade.price:.3f} | "
            f"Their size: ${trade.size:.2f} / ~${trader.estimated_bankroll:.0f} bankroll "
            f"= {their_pct:.1%} -> our size: ${our_size:.2f}"
        )

        return CopySignal(
            source_wallet=trader.wallet,
            source_trade=trade,
            our_side="BUY",
            our_outcome=trade.outcome,
            our_size=our_size,
            market_price=trade.price,
            trader_score=trader.score,
            reasoning=reasoning,
            timestamp=datetime.now(timezone.utc),
        )

    def mirror_exit(
        self, trader: ScoredTrader, trade: WalletTrade
    ) -> Optional[CopySignal]:
        """Create an exit signal from a trader's sell trade."""
        from datetime import datetime, timezone

        reasoning = (
            f"EXIT signal from {trader.pseudonym} (score={trader.score:.0f}) | "
            f"SELL {trade.outcome} — cumulative sell >=50% of entry | "
            f"Closing our mirrored position"
        )

        return CopySignal(
            source_wallet=trader.wallet,
            source_trade=trade,
            our_side="SELL",
            our_outcome=trade.outcome,
            our_size=0.0,  # Will be set to full position size by executor
            market_price=trade.price,
            trader_score=trader.score,
            reasoning=reasoning,
            timestamp=datetime.now(timezone.utc),
        )
