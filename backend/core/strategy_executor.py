"""Execute strategy decisions — create trades in paper mode, place orders in live mode."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.config import settings
from backend.models.database import SessionLocal, Trade, Signal, BotState
from backend.core.risk_manager import RiskManager
from backend.core.event_bus import _broadcast_event
from sqlalchemy import or_

logger = logging.getLogger("trading_bot.executor")
risk_manager = RiskManager()

# Serialize trade execution so bankroll reads and deductions are atomic.
# Two concurrent decisions would otherwise both pass risk validation with the
# same stale bankroll/exposure snapshot and double-count against limits.
_trade_execution_lock = asyncio.Lock()


async def execute_decision(
    decision: dict, strategy_name: str, db=None
) -> Optional[dict]:
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
    market_type = decision.get("market_type", "btc")
    market_end_date_str = decision.get("market_end_date")

    owns_db = db is None
    if owns_db:
        db = SessionLocal()
    try:
        async with _trade_execution_lock:
            event_slug = decision.get("slug") or decision.get("event_slug")
            filters = [
                Trade.settled.is_(False),
                Trade.trading_mode == settings.TRADING_MODE,
            ]
            if event_slug:
                filters.append(
                    or_(
                        Trade.market_ticker == market_ticker,
                        Trade.event_slug == event_slug,
                    )
                )
            else:
                filters.append(Trade.market_ticker == market_ticker)
            existing = db.query(Trade).filter(*filters).first()
            if existing:
                logger.info(
                    f"[{strategy_name}] Duplicate execution blocked for {market_ticker}/{event_slug}"
                )
                return None

            state = db.query(BotState).first()
            if not state or not state.is_running:
                logger.info(
                    f"[{strategy_name}] Bot not running, skipping decision for {market_ticker}"
                )
                return None

            if settings.TRADING_MODE == "paper":
                bankroll = (
                    state.paper_bankroll if state.paper_bankroll is not None else 0.0
                )
            elif settings.TRADING_MODE == "testnet":
                bankroll = (
                    state.testnet_bankroll
                    if state.testnet_bankroll is not None
                    else 0.0
                )
            else:
                bankroll = (
                    state.bankroll
                    if state.bankroll is not None
                    else settings.INITIAL_BANKROLL
                )
            current_exposure = _get_current_exposure(db)

            risk = risk_manager.validate_trade(
                size=size,
                current_exposure=current_exposure,
                bankroll=bankroll,
                confidence=confidence,
                market_ticker=market_ticker,
                db=db,
            )
            if not risk.allowed:
                logger.info(
                    f"[{strategy_name}] Risk rejected {market_ticker}: {risk.reason}"
                )
                return None

            adjusted_size = risk.adjusted_size

            # Enforce minimum order size for live/testnet trading
            MIN_ORDER_SIZE = 1.0
            if adjusted_size < MIN_ORDER_SIZE:
                logger.info(
                    f"[{settings.TRADING_MODE.upper()}][{strategy_name}] Order rejected for {market_ticker}: "
                    f"Size ${adjusted_size:.2f} below minimum ${MIN_ORDER_SIZE}"
                )
                return None

            clob_order_id = None
            fill_price = entry_price
            filled_size = None

            if settings.TRADING_MODE in ("testnet", "live"):
                if token_id:
                    try:
                        from backend.data.polymarket_clob import clob_from_settings

                        async with clob_from_settings() as clob:
                            await clob.create_or_derive_api_creds()
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
                            if (
                                hasattr(result, "filled_size")
                                and result.filled_size is not None
                            ):
                                filled_size = result.filled_size
                            logger.info(
                                f"[{settings.TRADING_MODE.upper()}][{strategy_name}] Order placed: {clob_order_id}"
                            )
                        else:
                            logger.warning(
                                f"[{settings.TRADING_MODE.upper()}][{strategy_name}] Order rejected for {market_ticker}: {result.error}"
                            )
                            return None
                    except Exception as clob_err:
                        logger.error(
                            f"[strategy_executor.execute_decision] {type(clob_err).__name__}: CLOB execution error for {market_ticker}: {clob_err}",
                            exc_info=True,
                        )
                        return None
                else:
                    logger.warning(
                        f"[{settings.TRADING_MODE.upper()}][{strategy_name}] No token_id for {market_ticker}, skipping order"
                    )
                    return None
            market_end_date = None
            if market_end_date_str:
                try:
                    market_end_date = datetime.fromisoformat(
                        market_end_date_str.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

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
                filled_size=filled_size,
                market_type=market_type,
                market_end_date=market_end_date,
            )

            db.add(trade)
            db.flush()

            if settings.TRADING_MODE == "paper" and state:
                state.paper_bankroll = max(
                    0.0, (state.paper_bankroll or 0.0) - adjusted_size
                )
            elif settings.TRADING_MODE == "testnet" and state:
                state.testnet_bankroll = max(
                    0.0, (state.testnet_bankroll or 0.0) - adjusted_size
                )

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
                token_id=token_id,
                executed=True,
            )
            db.add(signal_record)
            db.flush()
            trade.signal_id = signal_record.id

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

            try:
                _broadcast_event(
                    "trade_opened",
                    {
                        **trade_dict,
                        "trade_id": trade.id,
                        "entry_price": fill_price,
                        "mode": settings.TRADING_MODE,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"[strategy_executor.execute_decision] {type(e).__name__}: event broadcast failed (non-fatal): {e}",
                    exc_info=True,
                )

            logger.info(
                f"[{strategy_name}] Trade created: {direction.upper()} {market_ticker} "
                f"${adjusted_size:.2f} @ {fill_price:.3f} (mode={settings.TRADING_MODE})"
            )
            return trade_dict

    except Exception as exc:
        logger.exception(
            f"[strategy_executor.execute_decision] {type(exc).__name__}: execute_decision failed for {market_ticker}: {exc}"
        )
        try:
            db.rollback()
        except Exception as e:
            logger.warning(
                f"[strategy_executor.execute_decision] {type(e).__name__}: db.rollback failed (non-fatal): {e}",
                exc_info=True,
            )
        return None
    finally:
        if owns_db:
            db.close()


def _get_current_exposure(db) -> float:
    """Sum of open (unsettled) trade sizes for current trading mode."""
    from sqlalchemy import func

    result = (
        db.query(func.coalesce(func.sum(Trade.size), 0.0))
        .filter(Trade.settled.is_(False), Trade.trading_mode == settings.TRADING_MODE)
        .scalar()
    )
    return float(result or 0.0)


async def execute_decisions(
    decisions: list[dict], strategy_name: str, db=None
) -> list[dict]:
    """Execute multiple decisions, respecting per-scan limits."""
    MAX_TRADES_PER_CYCLE = 6
    results = []
    for d in decisions[:MAX_TRADES_PER_CYCLE]:
        result = await execute_decision(d, strategy_name, db=db)
        if result:
            results.append(result)
    return results


class StrategyExecutor:
    """Namespace for execute_decision / execute_decisions."""

    execute_decision = staticmethod(execute_decision)
    execute_decisions = staticmethod(execute_decisions)
