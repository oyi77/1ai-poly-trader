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
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("trading_bot")

# Import from extracted modules
from backend.strategies.wallet_sync import WalletWatcher
from backend.strategies.order_executor import (
    LeaderboardScorer,
    ScoredTrader,
    CopySignal,
    OrderExecutor,
)


class CopyTrader:
    """
    Orchestrates the copy trading strategy.

    - Refreshes leaderboard every 6h
    - Polls top wallets every 60s
    - Generates CopySignal for each new trade within risk limits
    """

    def __init__(
        self, bankroll: float = 1000.0, max_wallets: int = 10, min_score: float = 60.0
    ):
        self.bankroll = bankroll
        self.max_wallets = max_wallets
        self.min_score = min_score
        self._tracked: list[ScoredTrader] = []
        self._http: Optional[httpx.AsyncClient] = None
        self._watcher: Optional[WalletWatcher] = None
        self._scorer: Optional[LeaderboardScorer] = None
        self._executor: Optional[OrderExecutor] = None
        self._last_refresh: float = 0.0
        self._running = False

    async def start(self):
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )
        self._watcher = WalletWatcher(self._http)
        self._scorer = LeaderboardScorer(self._http)
        self._executor = OrderExecutor(self.bankroll)
        self._running = True
        await self._refresh_leaderboard()

    async def stop(self):
        self._running = False
        if self._http:
            await self._http.aclose()

    async def _refresh_leaderboard(self):
        """Refresh tracked wallets from leaderboard."""
        scored = await self._scorer.fetch_and_score(top_n=50)
        self._tracked = [t for t in scored if t.score >= self.min_score][
            : self.max_wallets
        ]
        self._last_refresh = asyncio.get_running_loop().time()
        logger.info(f"Tracking {len(self._tracked)} wallets after leaderboard refresh")

    async def poll_once(self) -> list[CopySignal]:
        """Poll all tracked wallets once. Returns new copy signals."""
        now = asyncio.get_running_loop().time()
        if now - self._last_refresh > 21600:
            await self._refresh_leaderboard()

        signals: list[CopySignal] = []
        seen_condition_ids: set = set()

        for trader in self._tracked:
            if not trader.wallet:
                continue
            try:
                new_buys, new_exits = await self._watcher.poll(trader.wallet)

                for trade in new_buys:
                    if trade.condition_id in seen_condition_ids:
                        continue
                    seen_condition_ids.add(trade.condition_id)
                    signal = self._executor.mirror_buy(trader, trade)
                    if signal:
                        signals.append(signal)

                for trade in new_exits:
                    signal = self._executor.mirror_exit(trader, trade)
                    if signal:
                        signals.append(signal)

            except Exception as e:
                logger.warning(f"Poll error for {trader.pseudonym}: {e}")

        return signals

    async def run_loop(self, poll_interval: int = 60, on_signal=None):
        """
        Main polling loop. Calls on_signal(signals) for each batch of new signals.
        Run this as an asyncio task.
        """
        logger.info(
            f"Copy trader loop started — polling {len(self._tracked)} wallets every {poll_interval}s"
        )
        while self._running:
            try:
                signals = await self.poll_once()
                if signals and on_signal:
                    await on_signal(signals)
            except Exception as e:
                logger.error(f"Copy trader loop error: {e}")
            await asyncio.sleep(poll_interval)


# ---------------------------------------------------------------------------
# BaseStrategy wrapper
# ---------------------------------------------------------------------------

from backend.strategies.base import BaseStrategy, CycleResult  # noqa: E402


class CopyTraderStrategy(BaseStrategy):
    """Wraps CopyTrader engine in the BaseStrategy plugin interface."""

    default_params = {
        "max_wallets": 20,
        "min_score": 60.0,
        "poll_interval": 60,
        "interval_seconds": 60,
    }

    name = "copy_trader"
    description = "Mirror top Polymarket whale traders proportionally to our bankroll"
    category = "copy_trading"

    def __init__(self, max_wallets: int = 20, min_score: float = 60.0):
        super().__init__()
        self._engine = CopyTrader(
            bankroll=10000, max_wallets=max_wallets, min_score=min_score
        )
        self._task: asyncio.Task | None = None

    async def market_filter(self, markets):
        return markets

    async def _get_active_wallets(self, ctx) -> list[str]:
        """
        Return union of: leaderboard top-N + enabled WalletConfig rows.
        WalletConfig rows are always included (user-curated, may not score well).
        """
        from backend.models.database import WalletConfig

        max_wallets = ctx.params.get("max_wallets", 20)
        min_score = ctx.params.get("min_score", 60.0)

        # 1. Get user-configured wallets
        user_wallets = [
            w.address
            for w in ctx.db.query(WalletConfig)
            .filter(WalletConfig.enabled == True)
            .all()
        ]

        # 2. Get leaderboard top wallets
        leaderboard_wallets = []
        try:
            traders = await self._engine._scorer.fetch_and_score(top_n=50)
            scored = [t for t in traders if t.score >= min_score]
            scored.sort(key=lambda t: t.score, reverse=True)
            leaderboard_wallets = [t.wallet for t in scored[:max_wallets]]
        except Exception as e:
            ctx.logger.warning(f"CopyTrader: leaderboard fetch failed: {e}")

        # 3. Union (preserve order: user-curated first, then leaderboard)
        seen = set()
        result = []
        for w in user_wallets + leaderboard_wallets:
            if w not in seen:
                seen.add(w)
                result.append(w)

        return result[: max_wallets * 2]  # cap at 2x to avoid runaway

    async def run_cycle(self, ctx):
        from backend.models.database import DecisionLog

        max_wallets = ctx.params.get("max_wallets", 20)
        min_score = ctx.params.get("min_score", 60.0)

        result = CycleResult(decisions_recorded=0, trades_attempted=0, trades_placed=0)
        try:
            if not self._engine._running:
                await self._engine.start()

            wallet_pool = await self._get_active_wallets(ctx)

            signals = await self._engine.poll_once()

            # Build a set of wallets that produced signals for fast lookup
            signaled_wallets = {s.source_wallet for s in signals} if signals else set()

            # Record a DecisionLog row for each wallet polled
            for wallet in wallet_pool:
                decision = "FOLLOW" if wallet in signaled_wallets else "SKIP"
                # Find matching signal for scoring breakdown if present
                wallet_signals = [
                    s for s in (signals or []) if s.source_wallet == wallet
                ]
                if wallet_signals:
                    signal_data = json.dumps(
                        {
                            "trader_score": wallet_signals[0].trader_score,
                            "signals_count": len(wallet_signals),
                            "outcomes": [s.our_side for s in wallet_signals],
                        }
                    )
                    reason = wallet_signals[0].reasoning
                else:
                    signal_data = json.dumps(
                        {"min_score": min_score, "max_wallets": max_wallets}
                    )
                    reason = f"No new trades detected for wallet {wallet[:10]}..."

                log_row = DecisionLog(
                    strategy=self.name,
                    market_ticker=wallet[:42],  # wallet address as identifier
                    decision=decision,
                    confidence=wallet_signals[0].trader_score / 100.0
                    if wallet_signals
                    else None,
                    signal_data=signal_data,
                    reason=reason,
                )
                ctx.db.add(log_row)

            ctx.db.commit()
            result.decisions_recorded = len(wallet_pool)
            result.trades_attempted = len(signals) if signals else 0

        except Exception as e:
            result.errors.append(str(e))
            ctx.logger.error(f"CopyTraderStrategy cycle error: {e}")
        return result
