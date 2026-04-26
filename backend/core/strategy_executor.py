"""Execute strategy decisions — create trades in paper mode, place orders in live mode."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from backend.config import settings
from backend.models.database import SessionLocal, Trade, Signal, BotState
from backend.core.risk_manager import RiskManager
from backend.core.event_bus import _broadcast_event
from backend.core.mode_context import get_context
from backend.core.alert_manager import AlertManager
from backend.core.validation import TradeValidator, SignalValidator, ValidationError, log_validation_error
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("trading_bot.executor")
risk_manager = RiskManager()

# Serialize trade execution so bankroll reads and deductions are atomic.
# Two concurrent decisions would otherwise both pass risk validation with the
# same stale bankroll/exposure snapshot and double-count against limits.
_trade_execution_lock = asyncio.Lock()


async def execute_decision(
    decision: dict, strategy_name: str, mode: str, db=None
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
            # Get mode execution context
            try:
                context = get_context(mode)
            except KeyError:
                logger.error(f"[{strategy_name}] No execution context for mode: {mode}")
                return None

            event_slug = decision.get("slug") or decision.get("event_slug")
            filters = [
                Trade.settled.is_(False),
                Trade.trading_mode == mode,
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

            state = db.query(BotState).filter_by(mode=mode).first()
            if not state or not state.is_running:
                logger.info(
                    f"[{strategy_name}] Bot not running, skipping decision for {market_ticker}"
                )
                return None

            if mode == "paper":
                bankroll = (
                    state.paper_bankroll if state.paper_bankroll is not None else 0.0
                )
            elif mode == "testnet":
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
            current_exposure = _get_current_exposure(db, trading_mode=mode)

            risk = context.risk_manager.validate_trade(
                size=size,
                current_exposure=current_exposure,
                bankroll=bankroll,
                confidence=confidence,
                market_ticker=market_ticker,
                db=db,
                mode=mode,
            )
            if not risk.allowed:
                logger.info(
                    f"[{strategy_name}] Risk rejected {market_ticker}: {risk.reason}"
                )
                return None

            adjusted_size = risk.adjusted_size

            # Paper mode is simulated — no real CLOB interaction, so allow smaller sizes
            MIN_ORDER_SIZE = 1.0 if mode == "paper" else 5.0
            if adjusted_size < MIN_ORDER_SIZE:
                logger.info(
                    f"[{mode.upper()}][{strategy_name}] Order rejected for {market_ticker}: "
                    f"Size ${adjusted_size:.2f} below minimum ${MIN_ORDER_SIZE}"
                )
                return None

            clob_order_id = None
            fill_price = entry_price
            filled_size = None
            alert_manager = AlertManager(db)

            if mode in ("testnet", "live"):
                is_kalshi = market_ticker.startswith("KX") or platform == "kalshi"

                if is_kalshi:
                    # Kalshi markets use their own API, not Polymarket CLOB
                    try:
                        from backend.data.kalshi_client import KalshiClient
                        client = KalshiClient()
                        logger.info(
                            f"[{mode.upper()}][{strategy_name}] Kalshi order simulated for {market_ticker} (live Kalshi order placement TBD)"
                        )
                    except Exception as kalshi_err:
                        logger.error(
                            f"[strategy_executor] Kalshi execution error for {market_ticker}: {kalshi_err}"
                        )
                        return None
                    # No CLOB order ID for Kalshi; simulate fill at entry price
                    clob_order_id = None
                    fill_price = entry_price
                elif token_id:
                    try:
                        async with context.clob_client as clob:
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
                                
                                alert_manager.check_high_slippage(
                                    trade_id=0,
                                    expected_price=entry_price,
                                    actual_price=fill_price,
                                    position_value=adjusted_size,
                                    mode=mode,
                                )
                            if (
                                hasattr(result, "filled_size")
                                and result.filled_size is not None
                            ):
                                filled_size = result.filled_size
                            logger.info(
                                f"[{mode.upper()}][{strategy_name}] Order placed: {clob_order_id}"
                            )
                        else:
                            logger.warning(
                                f"[{mode.upper()}][{strategy_name}] Order rejected for {market_ticker}: {result.error}"
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
                        f"[{mode.upper()}][{strategy_name}] No token_id for {market_ticker}, skipping order"
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

            slippage = abs(fill_price - entry_price) / entry_price if entry_price > 0 else 0.0
            fee = None

            trade_data = {
                "market_ticker": market_ticker,
                "platform": platform,
                "direction": direction,
                "entry_price": fill_price,
                "size": adjusted_size,
                "model_probability": model_probability,
                "market_price_at_entry": entry_price,
                "edge_at_entry": edge,
                "trading_mode": mode,
                "confidence": confidence,
                "result": "pending",
            }
            
            try:
                TradeValidator.validate_trade_data(trade_data)
            except ValidationError as e:
                log_validation_error(e, context=f"execute_decision:{strategy_name}")
                logger.error(f"[{strategy_name}] Trade validation failed: {e.message}")
                return None

            trade = Trade(
                market_ticker=market_ticker,
                platform=platform,
                direction=direction,
                entry_price=fill_price,
                size=adjusted_size,
                model_probability=model_probability,
                market_price_at_entry=entry_price,
                edge_at_entry=edge,
                trading_mode=mode,
                strategy=strategy_name,
                confidence=confidence,
                clob_order_id=clob_order_id,
                filled_size=filled_size,
                fee=fee,
                slippage=slippage,
                market_type=market_type,
                market_end_date=market_end_date,
            )

            db.add(trade)
            db.flush()

            from backend.models.audit_logger import log_trade_created
            log_trade_created(
                db=db,
                trade_id=trade.id,
                trade_data={
                    "market_ticker": market_ticker,
                    "direction": direction,
                    "entry_price": fill_price,
                    "size": adjusted_size,
                    "trading_mode": mode,
                    "strategy": strategy_name,
                    "confidence": confidence,
                    "edge": edge,
                    "clob_order_id": clob_order_id,
                },
                user_id=f"strategy:{strategy_name}",
            )

            if mode == "paper" and state:
                state.paper_bankroll = max(
                    0.0, (state.paper_bankroll or 0.0) - adjusted_size
                )
                state.paper_trades = (state.paper_trades or 0) + 1
            elif mode == "testnet" and state:
                state.testnet_bankroll = max(
                    0.0, (state.testnet_bankroll or 0.0) - adjusted_size
                )
                state.testnet_trades = (state.testnet_trades or 0) + 1
            elif mode == "live" and state:
                state.bankroll = max(0.0, (state.bankroll or 0.0) - adjusted_size)
                state.total_trades = (state.total_trades or 0) + 1

            signal_data = {
                "direction": direction,
                "model_probability": model_probability,
                "market_price": entry_price,
                "edge": edge,
                "confidence": confidence,
                "kelly_fraction": 0.0,
                "suggested_size": adjusted_size,
            }
            
            try:
                SignalValidator.validate_signal_data(signal_data)
            except ValidationError as e:
                log_validation_error(e, context=f"execute_decision:signal:{strategy_name}")
                logger.error(f"[{strategy_name}] Signal validation failed: {e.message}")
                return None

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
                execution_mode=mode,
                token_id=token_id,
                executed=True,
            )
            db.add(signal_record)
            db.flush()
            trade.signal_id = signal_record.id

            for _db_attempt in range(3):
                try:
                    db.commit()
                    break
                except OperationalError:
                    db.rollback()
                    if _db_attempt < 2:
                        time.sleep(0.5 * (_db_attempt + 1))
                    else:
                        raise

            trade_dict = {
                "id": trade.id,
                "market_ticker": market_ticker,
                "direction": direction,
                "fill_price": fill_price,
                "size": adjusted_size,
                "edge": edge,
                "confidence": confidence,
                "trading_mode": mode,
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
                        "mode": mode,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"[strategy_executor.execute_decision] {type(e).__name__}: event broadcast failed (non-fatal): {e}",
                    exc_info=True,
                )

            logger.info(
                f"[{strategy_name}] Trade created: {direction.upper()} {market_ticker} "
                f"${adjusted_size:.2f} @ {fill_price:.3f} (mode={mode})"
            )
            return trade_dict

    except OperationalError as exc:
        logger.error(
            f"[strategy_executor.execute_decision] OperationalError: execute_decision failed for {market_ticker}: {exc}",
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception as e:
            logger.warning(
                f"[strategy_executor.execute_decision] {type(e).__name__}: db.rollback failed after OperationalError (non-fatal): {e}",
                exc_info=True,
            )
        return None
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


def _get_current_exposure(db, trading_mode: str = None) -> float:
    """Sum of open (unsettled) trade sizes for current trading mode."""
    from sqlalchemy import func

    mode = trading_mode or settings.TRADING_MODE

    result = (
        db.query(func.coalesce(func.sum(Trade.size), 0.0))
        .filter(Trade.settled.is_(False), Trade.trading_mode == mode)
        .scalar()
    )
    return float(result or 0.0)


async def execute_decisions(
    decisions: list[dict], strategy_name: str, mode: str, db=None
) -> list[dict]:
    """Execute multiple decisions, respecting per-scan limits."""
    MAX_TRADES_PER_CYCLE = 6
    results = []
    for d in decisions[:MAX_TRADES_PER_CYCLE]:
        result = await execute_decision(d, strategy_name, mode, db=db)
        if result:
            results.append(result)
    return results


class StrategyExecutor:
    """Namespace for execute_decision / execute_decisions."""

    execute_decision = staticmethod(execute_decision)
    execute_decisions = staticmethod(execute_decisions)
