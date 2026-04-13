"""
Global notification dispatch.
Call set_bot() once from orchestrator on startup.
All other modules call notify_*() without holding a bot reference.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.bot.telegram_bot import PolyEdgeBot

logger = logging.getLogger("trading_bot")
_bot: Optional["PolyEdgeBot"] = None


def set_bot(bot: "PolyEdgeBot") -> None:
    global _bot
    _bot = bot


def get_bot() -> Optional["PolyEdgeBot"]:
    return _bot


def _fire(coro) -> None:
    """Schedule a coroutine on the running event loop (best-effort, never raises)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(coro)
    except Exception as e:
        logger.debug(f"notify fire error: {e}")


def notify_btc_signal(signal, trade=None) -> None:
    if _bot:
        _fire(_bot.send_btc_signal(signal, trade))


def notify_trade_opened(trade) -> None:
    if _bot:
        _fire(_bot.send_trade_opened(trade))


def notify_trade_settled(trade) -> None:
    if _bot:
        _fire(_bot.send_trade_settled(trade))


def notify_scan_summary(total: int, actionable: int, placed: int) -> None:
    if _bot and (actionable > 0 or placed > 0):
        _fire(_bot.send_scan_summary(total, actionable, placed))


def notify_error(error: str, context: str = "") -> None:
    if _bot:
        _fire(_bot.send_error_alert(error, context))


def notify_high_confidence_signal(
    strategy: str,
    market_title: str,
    direction: str,
    confidence: float,
    edge: float,
    reasoning: str,
    market_url: str = "",
) -> None:
    """
    Send alert for high-confidence trading signals (confidence >= 0.75).
    Called by strategies when they generate strong signals.
    """
    if _bot:
        _fire(
            _bot.send_high_confidence_signal(
                strategy=strategy,
                market_title=market_title,
                direction=direction,
                confidence=confidence,
                edge=edge,
                reasoning=reasoning,
                market_url=market_url,
            )
        )
