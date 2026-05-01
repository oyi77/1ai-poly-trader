import logging
from sqlalchemy.orm import Session

from backend.core.outcome_repository import record_outcome
from backend.core.trading_calibration import TradingCalibration
from backend.core.thompson_sampler import ThompsonSampler
from backend.core.strategy_health import StrategyHealthMonitor
from backend.core.safe_param_tuner import SafeParamTuner

logger = logging.getLogger(__name__)

_calibration = TradingCalibration()
_sampler = ThompsonSampler()
_health_monitor = StrategyHealthMonitor()
_param_tuner = SafeParamTuner()


class OnlineLearner:
    def on_trade_settled(self, trade, db: Session) -> None:
        strategy = getattr(trade, "strategy", None)
        if not strategy or strategy == "unknown":
            try:
                from backend.models.database import TradeContext
                ctx = db.query(TradeContext).filter(TradeContext.trade_id == trade.id).first()
                if ctx and ctx.strategy_name:
                    strategy = ctx.strategy_name
            except Exception:
                pass
        strategy = strategy or "general_scanner"

        outcome = record_outcome(trade, db)
        if outcome is None:
            logger.warning(f"[OnlineLearner] Failed to record outcome for trade {getattr(trade, 'id', '?')}")
            return

        prob = getattr(trade, "model_probability", None)
        result = getattr(trade, "result", None)
        if prob is not None and result in ("win", "loss"):
            actual = 1 if result == "win" else 0
            _calibration.record(strategy, prob, actual)
            _sampler.update(strategy, won=(result == "win"))

        health = _health_monitor.assess(strategy, db)
        if health.get("status") == "killed":
            logger.warning(f"[OnlineLearner] Strategy '{strategy}' killed by health monitor")
            return

        _param_tuner.revert_if_degraded(strategy, db)

    def run_cycle(self, strategy: str, db: Session) -> None:
        health = _health_monitor.assess(strategy, db)
        if health.get("status") == "killed":
            return

        _param_tuner.revert_if_degraded(strategy, db)
        _param_tuner.tune(strategy, db)

    def get_allocation(self, strategies: list, total_capital: float = 1000.0) -> dict:
        return _sampler.allocate(strategies, total_capital)

    def get_calibrated_prob(self, strategy: str, raw_prob: float) -> float:
        return _calibration.calibrate_probability(strategy, raw_prob)

    def get_strategy_rankings(self) -> dict[str, float]:
        try:
            return self.get_allocation(
                ["btc_momentum", "weather_emos", "btc_oracle", "copy_trader",
                 "market_maker", "kalshi_arb", "bond_scanner", "whale_pnl",
                 "realtime_scanner"], total_capital=1.0)
        except Exception:
            return {}
