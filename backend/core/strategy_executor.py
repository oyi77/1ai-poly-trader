"""Execute strategy decisions — create trades in paper mode, place orders in live mode."""
import logging
from datetime import datetime
from typing import Optional

from backend.config import settings
from backend.models.database import SessionLocal, Trade, Signal, BotState
from backend.core.risk_manager import RiskManager
from backend.core.event_bus import _broadcast_event

logger = logging.getLogger("trading_bot.executor")
risk_manager = RiskManager()


async def execute_decision(decision: dict, strategy_name: str) -> Optional[dict]:
    """
    Execute a single strategy decision.

    decision dict should have:
      - market_ticker: str
      - direction: str ("yes"/"no"/"up"/"down")
      - size: float (USD)
      - entry_price: float (market price, 0-1)
      - edge: float
      - confidence: float
      - model_probability: float (optional)
      - token_id: str (optional, for live CLOB orders)
      - platform: str (optional, default "polymarket")
      - reasoning: str (optional)
    """
    market_ticker = decision.get("market_ticker", "")
    direction = decision.get("direction", "")
    size = float(decision.get("size", 0.0))
    entry_price = float(decision.get("entry_price", 0.5))
    edge = float(decision.get("edge", 0.0))
    confidence = float(decision.get("confidence", 0.0))
    model_probability = float(decision.get("model_probability", confidence))
    token_id = decision.get("token_id")
    platform = decision.get("platform", "polymarket")
    reasoning = decision.get("reasoning", "")

    db = SessionLocal()
    try:
        # 1. Get current bot state
        state = db.query(BotState).first()
        if not state or not state.is_running:
            logger.info(f"[{strategy_name}] Bot not running, skipping decision for {market_ticker}")
            return None

        bankroll = state.bankroll if settings.TRADING_MODE != "paper" else state.paper_bankroll
        current_exposure = _get_current_exposure(db)

        # 2. Run risk validation
        risk = risk_manager.validate_trade(
            size=size,
            current_exposure=current_exposure,
            bankroll=bankroll,
            confidence=confidence,
            market_ticker=market_ticker,
        )
        if not risk.allowed:
            logger.info(f"[{strategy_name}] Risk rejected {market_ticker}: {risk.reason}")
            return None

        adjusted_size = risk.adjusted_size

        # 3. Determine trading mode and execute
        clob_order_id = None
        fill_price = entry_price

        if settings.TRADING_MODE in ("testnet", "live"):
            if token_id:
                try:
                    from backend.data.polymarket_clob import clob_from_settings
                    async with clob_from_settings() as clob:
                        result = await clob.place_limit_order(
                            token_id=token_id,
                            side="BUY",
                            price=entry_price,
                            size=adjusted_size,
                        )
                    if result.success:
                        clob_order_id = result.order_id
                        if result.fill_price:
                            fill_price = result.fill_price
                        logger.info(f"[{settings.TRADING_MODE.upper()}][{strategy_name}] Order placed: {clob_order_id}")
                    else:
                        logger.warning(f"[{settings.TRADING_MODE.upper()}][{strategy_name}] Order rejected for {market_ticker}: {result.error}")
                        return None
                except Exception as clob_err:
                    logger.error(f"[{strategy_name}] CLOB execution error for {market_ticker}: {clob_err}")
                    return None
            else:
                logger.warning(f"[{settings.TRADING_MODE.upper()}][{strategy_name}] No token_id for {market_ticker}, skipping order")
                return None
        # paper mode: simulate fill at entry_price (fill_price already set)

        # 4. Create Trade record
        trade = Trade(
            market_ticker=market_ticker,
            platform=platform,
            direction=direction,
            entry_price=fill_price,
            size=adjusted_size,
            model_probability=model_probability,
            market_price_at_entry=entry_price,
            edge_at_entry=edge,
            trading_mode=settings.TRADING_MODE,
            strategy=strategy_name,
            confidence=confidence,
            clob_order_id=clob_order_id,
        )

        db.add(trade)
        db.flush()  # get trade.id

        # 5. Create Signal record for calibration tracking
        signal_record = Signal(
            market_ticker=market_ticker,
            platform=platform,
            direction=direction,
            model_probability=model_probability,
            market_price=entry_price,
            edge=edge,
            confidence=confidence,
            kelly_fraction=0.0,
            suggested_size=adjusted_size,
            reasoning=reasoning,
            track_name=strategy_name,
            execution_mode=settings.TRADING_MODE,
            executed=True,
        )
        db.add(signal_record)
        db.flush()
        trade.signal_id = signal_record.id

        # 6. Update BotState
        if settings.TRADING_MODE == "paper":
            state.paper_bankroll = max(0.0, (state.paper_bankroll or 0.0) - adjusted_size)
            state.paper_trades = (state.paper_trades or 0) + 1
        else:
            state.bankroll = max(0.0, state.bankroll - adjusted_size)
            state.total_trades = (state.total_trades or 0) + 1

        db.commit()

        trade_dict = {
            "id": trade.id,
            "market_ticker": market_ticker,
            "direction": direction,
            "fill_price": fill_price,
            "size": adjusted_size,
            "edge": edge,
            "confidence": confidence,
            "trading_mode": settings.TRADING_MODE,
            "clob_order_id": clob_order_id,
            "strategy": strategy_name,
        }

        # 7. Broadcast trade event
        try:
            _broadcast_event("trade_opened", {
                **trade_dict,
                "trade_id": trade.id,
                "entry_price": fill_price,
                "mode": settings.TRADING_MODE,
            })
        except Exception:
            pass

        logger.info(
            f"[{strategy_name}] Trade created: {direction.upper()} {market_ticker} "
            f"${adjusted_size:.2f} @ {fill_price:.3f} (mode={settings.TRADING_MODE})"
        )
        return trade_dict

    except Exception as exc:
        logger.exception(f"[{strategy_name}] execute_decision failed for {market_ticker}: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def _get_current_exposure(db) -> float:
    """Sum of open (unsettled) trade sizes."""
    from sqlalchemy import func
    result = db.query(func.coalesce(func.sum(Trade.size), 0.0)).filter(
        Trade.settled == False
    ).scalar()
    return float(result or 0.0)


async def execute_decisions(decisions: list[dict], strategy_name: str) -> list[dict]:
    """Execute multiple decisions, respecting per-scan limits."""
    MAX_TRADES_PER_CYCLE = 2
    results = []
    for d in decisions[:MAX_TRADES_PER_CYCLE]:
        result = await execute_decision(d, strategy_name)
        if result:
            results.append(result)
    return results
