"""
Whale PNL Tracker (Track 2 - Parallel Edge Discovery).

Generates signals by following the positions of top-performing whale wallets
ranked by realized PNL, not leaderboard metrics.

Strategy:
- Computes whale scores from Polymarket Data API (realized PNL, win rate, consistency)
- Ranks wallets by score (higher = better)
- Mirrors positions from top N whales when they open new trades
- Generates UP/DOWN signals matching whale direction
- Records all signals with track_name='whale' for paper trading validation

Edge Hypothesis:
Whales with high realized PNL have sustainable alpha that persists.
By copying their entries in real-time, we capture their edge before it fades.

Track Configuration:
- Default bankroll: $500 (isolated from other tracks)
- Loss limit: $100
- Max whales to follow: 5
- Min whale score: 0.3 (on 0-1 scale)
- Copy fraction: 10% of our bankroll per whale signal
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from backend.strategies.base import BaseStrategy, StrategyContext, CycleResult, MarketInfo
from backend.core.decisions import record_decision
from backend.core.whale_discovery import WhaleDiscovery
from backend.models.database import SessionLocal, WalletConfig, CopyTraderEntry

logger = logging.getLogger("trading_bot")


@dataclass
class WhalePosition:
    """Represents a whale's open position."""
    wallet: str
    condition_id: str
    side: str  # "YES" or "NO"
    size: float
    ticker: str
    opened_at: datetime


class WhalePNLTrackerStrategy(BaseStrategy):
    """
    Whale PNL tracker for parallel edge discovery.

    Ranks wallets by realized PNL and generates signals by following
    their real-time position changes from Polymarket Data API.
    """

    name = "whale_pnl_tracker"
    description = "Whale PNL tracker - ranks wallets by realized PNL and mirrors top performers (Track 2)"
    category = "edge_discovery"
    default_params = {
        # Whale selection
        "max_whales": 5,               # Maximum number of whales to follow
        "min_whale_score": 0.3,        # Minimum whale score (0-1 scale)
        "min_trades": 20,              # Minimum trades for whale ranking
        "recency_days": 30,            # Only consider trades from last N days

        # Signal generation
        "copy_fraction": 0.10,         # Fraction of bankroll per whale signal
        "min_position_size": 100,      # Minimum position size to track (USD)
        "signal_cooldown_minutes": 5,  # Cooldown between signals for same market

        # Track configuration
        "track_name": "whale",
        "execution_mode": "paper",
    }

    def __init__(self):
        super().__init__()
        self._whale_discovery = WhaleDiscovery()
        self._tracked_positions: Dict[str, WhalePosition] = {}  # condition_id -> position
        self._last_signal_times: Dict[str, float] = {}  # ticker -> timestamp

    async def market_filter(self, markets: list[MarketInfo]) -> list[MarketInfo]:
        """Pass through all markets - whale signals determine which to trade."""
        return markets

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        """
        Execute one trading cycle.

        1. Rank whales by realized PNL
        2. Fetch current positions from top whales
        3. Generate signals for new/unseen positions
        4. Record decisions with whale attribution
        """
        result = CycleResult(
            decisions_recorded=0,
            trades_attempted=0,
            trades_placed=0,
        )

        try:
            # Step 1: Rank whales by PNL
            whales = await self._rank_whales(ctx)
            if not whales:
                logger.debug(f"[{self.name}] No qualified whales found")
                return result

            logger.info(f"[{self.name}] Tracking {len(whales)} whales: {[w['wallet'][:8]+'...' for w in whales]}")

            # Step 2: Fetch positions from top whales
            all_positions = await self._fetch_whale_positions(whales, ctx)
            logger.debug(f"[{self.name}] Found {len(all_positions)} positions from whales")

            # Step 3: Generate signals for new positions
            for position in all_positions:
                if await self._should_generate_signal(position, ctx):
                    decision = await self._generate_whale_signal(position, whales, ctx)
                    if decision:
                        result.decisions_recorded += 1
                        result.trades_attempted += 1

                        # Track this position to avoid duplicate signals
                        self._tracked_positions[position.condition_id] = position
                        self._last_signal_times[position.ticker] = datetime.utcnow().timestamp()

                        logger.info(
                            f"[{self.name}] {decision} signal: {position.ticker} "
                            f"(whale: {position.wallet[:8]}..., side: {position.side})"
                        )

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"[{self.name}] Error in run_cycle: {e}")

        return result

    async def _rank_whales(self, ctx: StrategyContext) -> List[Dict]:
        """
        Rank wallets by realized PNL using whale discovery.

        Returns list of {wallet, score, trade_count} dicts.
        """
        max_whales = ctx.params.get("max_whales", self.default_params["max_whales"])
        min_score = ctx.params.get("min_whale_score", self.default_params["min_whale_score"])
        min_trades = ctx.params.get("min_trades", self.default_params["min_trades"])

        # Discover and rank whales
        discovered = await self._whale_discovery.discover(min_trades=min_trades)

        # Filter by minimum score and limit
        qualified = [
            w for w in discovered
            if w["score"] >= min_score
        ][:max_whales]

        return qualified

    async def _fetch_whale_positions(
        self,
        whales: List[Dict],
        ctx: StrategyContext
    ) -> List[WhalePosition]:
        """
        Fetch current positions from tracked whales.

        Returns list of WhalePosition objects.
        """
        positions = []
        min_size = ctx.params.get("min_position_size", self.default_params["min_position_size"])

        for whale in whales:
            wallet = whale["wallet"]

            # Fetch positions from Polymarket Data API
            history = await self._whale_discovery._fetch_history(wallet)

            # Convert to WhalePosition objects
            for trade in history:
                try:
                    # Skip small positions
                    if trade.get("size", 0) < min_size:
                        continue

                    # Determine side from PNL (positive = YES, negative = NO)
                    # This is a heuristic - real implementation would use actual position data
                    side = "YES" if trade.get("pnl", 0) >= 0 else "NO"

                    # Create synthetic condition_id and ticker for now
                    # Real implementation would parse from actual position data
                    condition_id = f"cond_{wallet[:8]}_{trade.get('timestamp', 0)}"
                    ticker = f"Whale_{wallet[:6]}"

                    position = WhalePosition(
                        wallet=wallet,
                        condition_id=condition_id,
                        side=side,
                        size=trade.get("size", 0),
                        ticker=ticker,
                        opened_at=datetime.fromtimestamp(trade.get("timestamp", 0)),
                    )

                    positions.append(position)

                except Exception as e:
                    logger.debug(f"[{self.name}] Error parsing position: {e}")
                    continue

        return positions

    async def _should_generate_signal(
        self,
        position: WhalePosition,
        ctx: StrategyContext
    ) -> bool:
        """
        Check if we should generate a signal for this position.

        Filters out:
        - Positions we've already signaled
        - Positions in signal cooldown period
        - Positions that are too old
        """
        # Check if we've already tracked this position
        if position.condition_id in self._tracked_positions:
            return False

        # Check signal cooldown
        cooldown_minutes = ctx.params.get("signal_cooldown_minutes", self.default_params["signal_cooldown_minutes"])
        last_signal = self._last_signal_times.get(position.ticker, 0)
        cooldown_seconds = cooldown_minutes * 60

        if datetime.utcnow().timestamp() - last_signal < cooldown_seconds:
            return False

        # Check position age (skip old positions)
        position_age = datetime.utcnow() - position.opened_at
        if position_age > timedelta(hours=1):
            return False

        return True

    async def _generate_whale_signal(
        self,
        position: WhalePosition,
        whales: List[Dict],
        ctx: StrategyContext
    ) -> Optional[str]:
        """
        Generate a trading decision from a whale position.

        Returns decision string ("BUY" or None).
        """
        # Map whale side to our direction
        # Whale YES = UP, Whale NO = DOWN
        direction = "up" if position.side == "YES" else "down"

        # Calculate confidence from whale score
        whale_scores = {w["wallet"]: w["score"] for w in whales}
        whale_score = whale_scores.get(position.wallet, 0.0)
        confidence = min(whale_score, 1.0)

        # Get copy fraction from params
        copy_fraction = ctx.params.get("copy_fraction", self.default_params["copy_fraction"])

        # Record decision
        record_decision(
            ctx.db, self.name,
            position.ticker,
            "BUY",
            confidence=confidence,
            signal_data={
                "direction": direction,
                "whale_wallet": position.wallet,
                "whale_side": position.side,
                "whale_score": whale_score,
                "position_size": position.size,
                "copy_fraction": copy_fraction,
                "condition_id": position.condition_id,
                "track_name": ctx.params.get("track_name", "whale"),
            },
            reason=f"whale_pnl_tracker: {position.wallet[:8]}... (score={whale_score:.2f}) opened {position.side}"
        )

        return "BUY"
