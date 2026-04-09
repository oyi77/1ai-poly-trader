"""Backtesting engine — simulate strategy execution against historical market data."""
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.database import Trade, Signal, SessionLocal

logger = logging.getLogger("trading_bot.backtest")


@dataclass
class BacktestConfig:
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_bankroll: float = 100.0
    kelly_fraction: float = 0.0625
    max_trade_size: float = 10.0
    max_position_fraction: float = 0.10
    max_total_exposure: float = 0.60
    daily_loss_limit: float = 15.0


@dataclass
class BacktestTrade:
    timestamp: datetime
    market_ticker: str
    direction: str
    entry_price: float
    size: float
    edge: float
    settlement_value: Optional[float] = None
    pnl: Optional[float] = None
    settled: bool = False


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[BacktestTrade]
    equity_curve: list[dict]  # [{timestamp, bankroll}]
    total_pnl: float
    total_trades: int
    winning_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    avg_edge: float
    avg_trade_size: float
    final_bankroll: float
    return_pct: float


class BacktestEngine:
    """Simulate strategy execution against historical market data."""

    def __init__(self, config: BacktestConfig):
        self.config = config

    async def run(self, db: Session = None) -> BacktestResult:
        """
        Main entry point. Fetches historical signals from DB for the strategy
        and date range. Falls back to historical trades if no signals found.
        """
        _owned = db is None
        if _owned:
            db = SessionLocal()
        try:
            signals = self._fetch_signals(db)
            if signals:
                logger.info(
                    f"[backtester] Running signal-based backtest: {len(signals)} signals "
                    f"for strategy={self.config.strategy_name}"
                )
                return self._simulate_from_signals(signals, db)
            else:
                logger.info(
                    f"[backtester] No signals found for strategy={self.config.strategy_name}, "
                    f"falling back to trade replay"
                )
                return await self.run_from_trades(db)
        finally:
            if _owned:
                db.close()

    def _fetch_signals(self, db: Session) -> list[Signal]:
        """Fetch historical signals matching strategy and date range."""
        query = (
            db.query(Signal)
            .filter(
                Signal.timestamp >= self.config.start_date,
                Signal.timestamp <= self.config.end_date,
            )
            .order_by(Signal.timestamp.asc())
        )
        if self.config.strategy_name:
            query = query.filter(
                Signal.reasoning.contains(self.config.strategy_name)
            )
        return query.all()

    def _simulate_from_signals(
        self, signals: list[Signal], db: Session
    ) -> BacktestResult:
        """Simulate trades from signal records."""
        bankroll = self.config.initial_bankroll
        equity_curve: list[dict] = []
        bt_trades: list[BacktestTrade] = []

        # Track daily loss per calendar date
        daily_pnl: dict[date, float] = {}
        total_exposure = 0.0

        for sig in signals:
            if sig.edge is None or sig.edge <= 0:
                continue

            trade_date = sig.timestamp.date()

            # Daily loss limit check
            day_loss = daily_pnl.get(trade_date, 0.0)
            if day_loss <= -self.config.daily_loss_limit:
                logger.debug(
                    f"[backtester] Daily loss limit hit on {trade_date}, skipping signal"
                )
                continue

            # Position sizing
            kelly_size = bankroll * self.config.kelly_fraction * sig.edge
            size = min(
                kelly_size,
                self.config.max_trade_size,
                bankroll * self.config.max_position_fraction,
            )
            if size <= 0:
                continue

            # Total exposure check
            if (total_exposure + size) / bankroll > self.config.max_total_exposure:
                continue

            entry_price = sig.market_price if getattr(sig, "market_price", None) is not None else 0.5
            settlement_value = sig.settlement_value

            # Determine PnL from settlement
            pnl: Optional[float] = None
            settled = False
            if settlement_value is not None:
                settled = True
                if sig.direction == "up":
                    pnl = size * (1.0 - entry_price) if settlement_value == 1.0 else -size
                else:
                    pnl = size * (1.0 - entry_price) if settlement_value == 0.0 else -size
            elif sig.outcome_correct is not None:
                settled = True
                if sig.outcome_correct:
                    pnl = size * sig.edge
                else:
                    pnl = -size

            bt_trade = BacktestTrade(
                timestamp=sig.timestamp,
                market_ticker=sig.market_ticker,
                direction=sig.direction or "up",
                entry_price=entry_price,
                size=size,
                edge=sig.edge,
                settlement_value=settlement_value,
                pnl=pnl,
                settled=settled,
            )
            bt_trades.append(bt_trade)

            if pnl is not None:
                bankroll += pnl
                total_exposure = max(0.0, total_exposure - size)
                daily_pnl[trade_date] = daily_pnl.get(trade_date, 0.0) + pnl
            else:
                total_exposure += size

            equity_curve.append(
                {
                    "timestamp": sig.timestamp.isoformat(),
                    "bankroll": round(bankroll, 4),
                }
            )

        metrics = self._calculate_metrics(bt_trades, equity_curve, self.config.initial_bankroll)
        return BacktestResult(
            config=self.config,
            trades=bt_trades,
            equity_curve=equity_curve,
            **metrics,
        )

    async def run_from_trades(self, db: Session = None) -> BacktestResult:
        """
        Backtest using actual historical Trade records from the DB.
        Replays settled trades chronologically with the config's risk parameters.
        """
        _owned = db is None
        if _owned:
            db = SessionLocal()
        try:
            trades = (
                db.query(Trade)
                .filter(
                    Trade.timestamp >= self.config.start_date,
                    Trade.timestamp <= self.config.end_date,
                    Trade.settled == True,
                )
                .order_by(Trade.timestamp.asc())
                .all()
            )

            if self.config.strategy_name:
                trades = [
                    t for t in trades
                    if t.strategy == self.config.strategy_name
                ]

            logger.info(f"[backtester] Replaying {len(trades)} settled trades")

            bankroll = self.config.initial_bankroll
            equity_curve: list[dict] = []
            bt_trades: list[BacktestTrade] = []

            daily_pnl: dict[date, float] = {}

            for trade in trades:
                trade_date = trade.timestamp.date()

                day_loss = daily_pnl.get(trade_date, 0.0)
                if day_loss <= -self.config.daily_loss_limit:
                    continue

                edge = trade.edge_at_entry or 0.02
                kelly_size = bankroll * self.config.kelly_fraction * edge
                size = min(
                    kelly_size,
                    self.config.max_trade_size,
                    bankroll * self.config.max_position_fraction,
                )
                if size <= 0:
                    continue

                entry_price = trade.entry_price or 0.5
                settlement_value = trade.settlement_value

                pnl: Optional[float] = None
                if settlement_value is not None:
                    if trade.direction == "up":
                        pnl = size * (1.0 - entry_price) if settlement_value == 1.0 else -size
                    else:
                        pnl = size * (1.0 - entry_price) if settlement_value == 0.0 else -size
                elif trade.pnl is not None:
                    # Scale original pnl proportionally
                    orig_size = trade.size or size
                    scale = size / orig_size if orig_size > 0 else 1.0
                    pnl = trade.pnl * scale

                bt_trade = BacktestTrade(
                    timestamp=trade.timestamp,
                    market_ticker=trade.market_ticker,
                    direction=trade.direction or "up",
                    entry_price=entry_price,
                    size=size,
                    edge=edge,
                    settlement_value=settlement_value,
                    pnl=pnl,
                    settled=True,
                )
                bt_trades.append(bt_trade)

                if pnl is not None:
                    bankroll += pnl
                    daily_pnl[trade_date] = daily_pnl.get(trade_date, 0.0) + pnl

                equity_curve.append(
                    {
                        "timestamp": trade.timestamp.isoformat(),
                        "bankroll": round(bankroll, 4),
                    }
                )

            metrics = self._calculate_metrics(bt_trades, equity_curve, self.config.initial_bankroll)
            return BacktestResult(
                config=self.config,
                trades=bt_trades,
                equity_curve=equity_curve,
                **metrics,
            )
        finally:
            if _owned:
                db.close()

    def _calculate_metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[dict],
        initial_bankroll: float,
    ) -> dict:
        """Compute performance metrics from completed trades."""
        settled = [t for t in trades if t.pnl is not None]
        wins = [t for t in settled if t.pnl > 0]
        losses = [t for t in settled if t.pnl <= 0]

        total_trades = len(settled)
        winning_trades = len(wins)
        total_pnl = sum(t.pnl for t in settled)
        final_bankroll = initial_bankroll + total_pnl
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        avg_edge = (
            sum(t.edge for t in trades) / len(trades) if trades else 0.0
        )
        avg_trade_size = (
            sum(t.size for t in trades) / len(trades) if trades else 0.0
        )
        return_pct = (
            (final_bankroll - initial_bankroll) / initial_bankroll * 100
            if initial_bankroll > 0
            else 0.0
        )

        # Max drawdown from equity curve peak-to-trough
        max_drawdown = 0.0
        if equity_curve:
            peak = equity_curve[0]["bankroll"]
            for point in equity_curve:
                b = point["bankroll"]
                if b > peak:
                    peak = b
                dd = (peak - b) / peak if peak > 0 else 0.0
                if dd > max_drawdown:
                    max_drawdown = dd

        # Sharpe ratio: mean(returns) / std(returns) * sqrt(252)
        sharpe_ratio = 0.0
        pnls = [t.pnl for t in settled]
        if len(pnls) > 1:
            mean_r = statistics.mean(pnls)
            std_r = statistics.stdev(pnls)
            if std_r > 0:
                sharpe_ratio = (mean_r / std_r) * (252 ** 0.5)

        return {
            "total_pnl": round(total_pnl, 4),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": round(win_rate, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe_ratio, 4),
            "avg_edge": round(avg_edge, 4),
            "avg_trade_size": round(avg_trade_size, 4),
            "final_bankroll": round(final_bankroll, 4),
            "return_pct": round(return_pct, 4),
        }
