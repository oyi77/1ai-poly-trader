"""
Copy Trader Strategy for PolyEdge.

Monitors top Polymarket traders (by leaderboard score) and mirrors
their trades proportionally to our bankroll.

Execution mode: auto_with_limits — trades execute within risk manager
bounds without Telegram confirmation. Post-execution alerts are sent.

Data flow:
  Polymarket Leaderboard → score top 50 → track top N wallets
  Every 60s: poll /trades per wallet → detect new trades → mirror proportionally
  Exit tracking: cumulative SELL >= 50% of original entry → mirror exit
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("trading_bot")

DATA_HOST = "https://data-api.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"


@dataclass
class ScoredTrader:
    wallet: str
    pseudonym: str
    profit_30d: float
    win_rate: float
    total_trades: int
    unique_markets: int
    estimated_bankroll: float  # sum of open positions + recent pnl — manual override via config
    score: float = 0.0

    @property
    def market_diversity(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return min(1.0, self.unique_markets / self.total_trades)


@dataclass
class WalletTrade:
    wallet: str
    condition_id: str
    outcome: str        # "YES" or "NO"
    side: str           # "BUY" or "SELL"
    price: float
    size: float         # USDC
    timestamp: str
    tx_hash: str = ""
    title: str = ""


@dataclass
class CopySignal:
    source_wallet: str
    source_trade: WalletTrade
    our_side: str
    our_outcome: str
    our_size: float           # Kelly-proportioned USDC size
    market_price: float
    trader_score: float
    reasoning: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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

    async def fetch_and_score(self, top_n: int = 50) -> list[ScoredTrader]:
        """Fetch leaderboard and return top_n scored traders."""
        try:
            resp = await self._http.get(f"{DATA_HOST}/leaderboard", params={"window": "30d"})
            resp.raise_for_status()
            entries = resp.json()
        except Exception as e:
            logger.error(f"Leaderboard fetch failed: {e}")
            return []

        if not entries:
            return []

        # Normalise raw values for scoring
        profits = [float(e.get("profit", 0)) for e in entries]

        max_profit = max(profits) if profits else 1.0
        max_profit = max_profit if max_profit > 0 else 1.0

        traders = []
        for e in entries[:top_n]:
            profit = float(e.get("profit", 0))
            win_rate = float(e.get("pnlPercentage", 0)) / 100
            trades = int(e.get("tradesCount", 0))

            # Estimate bankroll: open position values from Data API (best effort)
            est_bankroll = max(abs(profit) * 5, 1000.0)  # rough: assume profit is ~20% of bankroll

            trader = ScoredTrader(
                wallet=e.get("proxyWallet", e.get("address", "")),
                pseudonym=e.get("name", e.get("pseudonym", "unknown")),
                profit_30d=profit,
                win_rate=max(0.0, min(1.0, win_rate)),
                total_trades=trades,
                unique_markets=int(e.get("marketsTraded", trades)),  # fallback to trades
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
        logger.info(f"Scored {len(traders)} traders. Top: {traders[0].pseudonym} score={traders[0].score:.1f}")
        return traders



class WalletWatcher:
    """Polls a wallet's trade history for new trades."""

    def __init__(self, http: httpx.AsyncClient):
        self._http = http
        # wallet -> set of seen tx_hashes
        self._seen: dict[str, set[str]] = {}
        # wallet -> {condition_id+outcome -> cumulative_buy_size}
        self._entry_sizes: dict[str, dict[str, float]] = {}
        # wallet -> {condition_id+outcome -> cumulative_sell_size}
        self._sell_sizes: dict[str, dict[str, float]] = {}

    async def poll(self, wallet: str, limit: int = 100) -> tuple[list[WalletTrade], list[WalletTrade]]:
        """
        Poll wallet trades. Returns (new_buys, new_exits).
        new_exits: trades where cumulative SELL >= 50% of original entry.
        """
        try:
            resp = await self._http.get(
                f"{DATA_HOST}/trades",
                params={"user": wallet, "limit": limit, "takerOnly": "true"},
            )
            resp.raise_for_status()
            trades_raw = resp.json()
        except Exception as e:
            logger.warning(f"Poll failed for {wallet[:10]}...: {e}")
            return [], []

        if wallet not in self._seen:
            self._seen[wallet] = set()
            self._entry_sizes[wallet] = {}
            self._sell_sizes[wallet] = {}
            # Seed with existing trades (don't mirror history)
            for t in trades_raw:
                key = t.get("transactionHash", "") or t.get("id", "")
                self._seen[wallet].add(key)
            return [], []

        seen = self._seen[wallet]
        new_buys: list[WalletTrade] = []
        new_exits: list[WalletTrade] = []

        for t in trades_raw:
            tx = t.get("transactionHash", "") or t.get("id", "")
            if tx in seen:
                continue
            seen.add(tx)

            outcome_idx = t.get("outcomeIndex", 0)
            outcome = "YES" if outcome_idx == 0 else "NO"
            side = t.get("side", "BUY").upper()
            size = float(t.get("size", 0))
            price = float(t.get("price", 0))
            condition_id = t.get("conditionId", "")

            trade = WalletTrade(
                wallet=wallet,
                condition_id=condition_id,
                outcome=outcome,
                side=side,
                price=price,
                size=size,
                timestamp=t.get("timestamp", ""),
                tx_hash=tx,
                title=t.get("title", ""),
            )

            pos_key = f"{condition_id}:{outcome}"
            if side == "BUY":
                self._entry_sizes[wallet][pos_key] = (
                    self._entry_sizes[wallet].get(pos_key, 0) + size
                )
                new_buys.append(trade)
                logger.info(
                    f"New trade from {wallet[:10]}...: BUY {outcome} "
                    f"@ {price:.3f} size={size:.2f} | {trade.title[:40]}"
                )
            else:  # SELL
                self._sell_sizes[wallet][pos_key] = (
                    self._sell_sizes[wallet].get(pos_key, 0) + size
                )
                orig_entry = self._entry_sizes[wallet].get(pos_key, 0)
                cumulative_sell = self._sell_sizes[wallet][pos_key]

                if orig_entry > 0 and cumulative_sell >= 0.50 * orig_entry:
                    new_exits.append(trade)
                    logger.info(
                        f"Exit signal from {wallet[:10]}...: SELL {outcome} "
                        f"cumulative={cumulative_sell:.2f}/{orig_entry:.2f} "
                        f"({cumulative_sell/orig_entry:.0%}) | {trade.title[:40]}"
                    )

        return new_buys, new_exits


class CopyTrader:
    """
    Orchestrates the copy trading strategy.

    - Refreshes leaderboard every 6h
    - Polls top wallets every 60s
    - Generates CopySignal for each new trade within risk limits
    """

    def __init__(self, bankroll: float = 1000.0, max_wallets: int = 10, min_score: float = 60.0):
        self.bankroll = bankroll
        self.max_wallets = max_wallets
        self.min_score = min_score
        self._tracked: list[ScoredTrader] = []
        self._http: Optional[httpx.AsyncClient] = None
        self._watcher: Optional[WalletWatcher] = None
        self._scorer: Optional[LeaderboardScorer] = None
        self._last_refresh: float = 0.0
        self._running = False

    async def start(self):
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )
        self._watcher = WalletWatcher(self._http)
        self._scorer = LeaderboardScorer(self._http)
        self._running = True
        await self._refresh_leaderboard()

    async def stop(self):
        self._running = False
        if self._http:
            await self._http.aclose()

    async def _refresh_leaderboard(self):
        """Refresh tracked wallets from leaderboard."""
        scored = await self._scorer.fetch_and_score(top_n=50)
        self._tracked = [t for t in scored if t.score >= self.min_score][: self.max_wallets]
        self._last_refresh = asyncio.get_running_loop().time()
        logger.info(f"Tracking {len(self._tracked)} wallets after leaderboard refresh")

    async def poll_once(self) -> list[CopySignal]:
        """Poll all tracked wallets once. Returns new copy signals."""
        # Refresh leaderboard every 6 hours
        now = asyncio.get_running_loop().time()
        if now - self._last_refresh > 21600:
            await self._refresh_leaderboard()

        signals: list[CopySignal] = []

        for trader in self._tracked:
            if not trader.wallet:
                continue
            try:
                new_buys, new_exits = await self._watcher.poll(trader.wallet)

                for trade in new_buys:
                    signal = self._mirror_buy(trader, trade)
                    if signal:
                        signals.append(signal)

                for trade in new_exits:
                    signal = self._mirror_exit(trader, trade)
                    if signal:
                        signals.append(signal)

            except Exception as e:
                logger.warning(f"Poll error for {trader.pseudonym}: {e}")

        return signals

    def _mirror_buy(self, trader: ScoredTrader, trade: WalletTrade) -> Optional[CopySignal]:
        """Create a proportional buy signal from a trader's buy trade."""
        if trader.estimated_bankroll <= 0:
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
        )

    def _mirror_exit(self, trader: ScoredTrader, trade: WalletTrade) -> Optional[CopySignal]:
        """Create an exit signal from a trader's sell trade."""
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
        )

    async def run_loop(self, poll_interval: int = 60, on_signal=None):
        """
        Main polling loop. Calls on_signal(signals) for each batch of new signals.
        Run this as an asyncio task.
        """
        logger.info(f"Copy trader loop started — polling {len(self._tracked)} wallets every {poll_interval}s")
        while self._running:
            try:
                signals = await self.poll_once()
                if signals and on_signal:
                    await on_signal(signals)
            except Exception as e:
                logger.error(f"Copy trader loop error: {e}")
            await asyncio.sleep(poll_interval)
