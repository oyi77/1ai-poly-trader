"""Risk manager — validates trades against position size, exposure, drawdown, and confidence rules."""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from backend.config import settings
from backend.models.database import SessionLocal, Trade
from sqlalchemy import func

logger = logging.getLogger("trading_bot.risk")


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    adjusted_size: float


@dataclass
class DrawdownStatus:
    daily_pnl: float
    weekly_pnl: float
    daily_limit_pct: float
    weekly_limit_pct: float
    is_breached: bool
    breach_reason: str = ""


class RiskManager:
    def __init__(self, settings_obj=None):
        self.s = settings_obj or settings

    def validate_trade(
        self,
        size: float,
        current_exposure: float,
        bankroll: float,
        confidence: float,
        market_ticker: Optional[str] = None,
        slippage: Optional[float] = None,
    ) -> RiskDecision:
        if confidence < 0.5:
            return RiskDecision(False, f"confidence {confidence:.2f} below 0.5", 0.0)

        if self._daily_loss_exceeded():
            return RiskDecision(False, "daily loss limit hit", 0.0)

        drawdown = self.check_drawdown(bankroll)
        if drawdown.is_breached:
            return RiskDecision(False, f"drawdown breaker: {drawdown.breach_reason}", 0.0)

        if market_ticker and self._has_unsettled_trade(market_ticker):
            return RiskDecision(False, f"unsettled trade exists for {market_ticker}", 0.0)

        max_position = bankroll * self.s.MAX_POSITION_FRACTION
        adjusted = min(size, max_position)

        max_exposure = bankroll * self.s.MAX_TOTAL_EXPOSURE_FRACTION
        if current_exposure + adjusted > max_exposure:
            adjusted = max(0.0, max_exposure - current_exposure)
            if adjusted <= 0:
                return RiskDecision(False, "max exposure reached", 0.0)

        if slippage is not None and slippage > self.s.SLIPPAGE_TOLERANCE:
            return RiskDecision(False, f"slippage {slippage:.4f} > tolerance", 0.0)

        return RiskDecision(True, "ok", adjusted)

    def check_drawdown(self, bankroll: float) -> DrawdownStatus:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            day_start = now - timedelta(hours=24)
            week_start = now - timedelta(days=7)

            daily_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                Trade.settled == True,
                Trade.settlement_time >= day_start,
            ).scalar() or 0.0

            weekly_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                Trade.settled == True,
                Trade.settlement_time >= week_start,
            ).scalar() or 0.0

            daily_limit = bankroll * self.s.DAILY_DRAWDOWN_LIMIT_PCT
            weekly_limit = bankroll * self.s.WEEKLY_DRAWDOWN_LIMIT_PCT

            breach_reason = ""
            is_breached = False

            if daily_pnl <= -daily_limit:
                is_breached = True
                breach_reason = f"24h loss ${abs(daily_pnl):.2f} exceeds {self.s.DAILY_DRAWDOWN_LIMIT_PCT*100:.0f}% limit (${daily_limit:.2f})"
            elif weekly_pnl <= -weekly_limit:
                is_breached = True
                breach_reason = f"7d loss ${abs(weekly_pnl):.2f} exceeds {self.s.WEEKLY_DRAWDOWN_LIMIT_PCT*100:.0f}% limit (${weekly_limit:.2f})"

            return DrawdownStatus(
                daily_pnl=daily_pnl,
                weekly_pnl=weekly_pnl,
                daily_limit_pct=self.s.DAILY_DRAWDOWN_LIMIT_PCT,
                weekly_limit_pct=self.s.WEEKLY_DRAWDOWN_LIMIT_PCT,
                is_breached=is_breached,
                breach_reason=breach_reason,
            )
        except Exception:
            logger.exception("Drawdown check failed, blocking trade (fail-closed)")
            return DrawdownStatus(0.0, 0.0, self.s.DAILY_DRAWDOWN_LIMIT_PCT, self.s.WEEKLY_DRAWDOWN_LIMIT_PCT, True, "DB error during drawdown check")
        finally:
            db.close()

    def _daily_loss_exceeded(self) -> bool:
        db = SessionLocal()
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                Trade.settled == True,
                Trade.settlement_time >= today_start,
            ).scalar() or 0.0
            return daily_pnl <= -self.s.DAILY_LOSS_LIMIT
        except Exception:
            logger.exception("Risk check failed, blocking trade (fail-closed)")
            return True
        finally:
            db.close()

    def _has_unsettled_trade(self, market_ticker: str) -> bool:
        db = SessionLocal()
        try:
            count = db.query(func.count(Trade.id)).filter(
                Trade.market_ticker == market_ticker,
                Trade.settled == False,
            ).scalar() or 0
            return count > 0
        except Exception:
            logger.exception("Unsettled trade check failed, blocking trade")
            return True
        finally:
            db.close()
