"""
PolyEdge Orchestrator.

Wires together:
  - Telegram bot (weather confirm-mode, copy trade notify-mode)
  - Polymarket CLOB client (shared connection pool)
  - CopyTrader strategy loop
  - Weather scan job with Telegram alert dispatch
  - Scheduler (BTC + weather interval jobs)

Usage:
    orchestrator = Orchestrator()
    await orchestrator.start()
    # runs until KeyboardInterrupt / SIGTERM
    await orchestrator.stop()
"""
import asyncio
import logging
import signal
from typing import Optional

from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB, clob_from_settings

logger = logging.getLogger("trading_bot")


class Orchestrator:
    """Top-level coordinator. Create one per process."""

    def __init__(self):
        self._clob: Optional[PolymarketCLOB] = None
        self._bot = None           # PolyEdgeBot (optional)
        self._copy_trader = None   # CopyTrader
        self._copy_task: Optional[asyncio.Task] = None
        self._running = False

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start all subsystems."""
        self._running = True
        logger.info("Orchestrator starting...")

        # 1. CLOB client (shared pool)
        self._clob = clob_from_settings()
        await self._clob.__aenter__()

        # 2. Telegram bot (optional)
        if settings.TELEGRAM_BOT_TOKEN:
            from backend.bot.telegram_bot import bot_from_settings
            self._bot = bot_from_settings()
            self._bot.on_copy_trade = self._execute_weather_signal
            self._bot.on_pause = self._on_pause
            self._bot.on_resume = self._on_resume
            self._bot.on_mode_switch = self.on_mode_switch
            await self._bot.start()

        # 3. Copy trader
        from backend.strategies.copy_trader import CopyTrader
        self._copy_trader = CopyTrader(
            bankroll=settings.INITIAL_BANKROLL,
            max_wallets=10,
            min_score=60.0,
        )
        await self._copy_trader.start()

        # 4. Wire weather scan to use Telegram alerts
        self._patch_weather_job()

        # 5. Start scheduler (BTC + weather interval jobs)
        from backend.core.scheduler import start_scheduler
        start_scheduler()

        # 6. Copy trader run loop (async task)
        self._copy_task = asyncio.create_task(
            self._copy_trader.run_loop(
                poll_interval=60,
                on_signal=self._handle_copy_signals,
            ),
            name="copy_trader_loop",
        )

        logger.info("Orchestrator started.")

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("Orchestrator stopping...")
        self._running = False

        if self._copy_task and not self._copy_task.done():
            self._copy_task.cancel()
            try:
                await self._copy_task
            except asyncio.CancelledError:
                pass

        if self._copy_trader:
            await self._copy_trader.stop()

        if self._bot:
            await self._bot.stop()

        if self._clob:
            # Cancel open orders on shutdown (live mode only)
            if settings.TRADING_MODE == "live":
                await self._clob.cancel_all_orders()
            await self._clob.__aexit__(None, None, None)

        from backend.core.scheduler import stop_scheduler
        stop_scheduler()

        logger.info("Orchestrator stopped.")

    # =========================================================================
    # Scheduler patch — inject Telegram dispatch into weather job
    # =========================================================================

    def _patch_weather_job(self) -> None:
        """
        Replace weather_scan_and_trade_job in the scheduler module with a
        version that sends Telegram alerts for actionable signals.
        """
        import backend.core.scheduler as sched_mod
        bot = self._bot
        clob = self._clob

        original_job = sched_mod.weather_scan_and_trade_job

        async def patched_weather_job():
            """Weather job with Telegram dispatch."""
            from backend.core.weather_signals import scan_for_weather_signals
            from backend.core.scheduler import log_event

            signals = await scan_for_weather_signals()
            actionable = [s for s in signals if s.passes_threshold]

            log_event("data", f"Weather: {len(signals)} signals, {len(actionable)} actionable")

            if not actionable:
                return

            # Telegram confirm-mode: send alert with keyboard, wait for user press
            if bot and bot._bot:
                for signal in actionable[:3]:  # Alert top 3
                    try:
                        await bot.send_weather_signal(signal)
                        log_event("info", f"Telegram alert sent: {signal.market.city_name} {signal.direction.upper()}")
                    except Exception as e:
                        logger.warning(f"Failed to send weather alert: {e}")
            else:
                # No Telegram — auto-execute in paper mode
                if settings.TRADING_MODE == "paper":
                    await _auto_execute_weather(actionable[:3], clob)

            # Always persist to DB via original job logic (settlement tracking)
            try:
                await original_job()
            except Exception as e:
                logger.debug(f"Original weather job error (non-fatal): {e}")

        sched_mod.weather_scan_and_trade_job = patched_weather_job

    # =========================================================================
    # Signal handlers
    # =========================================================================

    async def _execute_weather_signal(self, signal) -> None:
        """
        Called when user presses COPY TRADE on a weather Telegram alert.
        Places order via CLOB client.
        """
        if not self._clob:
            raise RuntimeError("CLOB client not initialised")

        market = signal.market
        token_id = getattr(market, "token_id", "") or market.market_id
        side = "BUY"  # Always BUY the correct outcome token (token_id selects YES vs NO)
        price = market.yes_price if signal.direction == "yes" else market.no_price

        result = await self._clob.place_limit_order(
            token_id=token_id,
            side=side,
            price=price,
            size=signal.suggested_size,
        )

        if not result.success:
            raise RuntimeError(result.error or "Order rejected")

        logger.info(
            f"Weather trade executed: {side} ${signal.suggested_size:.2f} @ {price:.3f} "
            f"order={result.order_id}"
        )
        return result

    async def _handle_copy_signals(self, signals: list) -> None:
        """
        Called by CopyTrader.run_loop for each batch of new signals.
        Auto-executes within risk limits, sends Telegram notification after.
        """
        for sig in signals:
            try:
                result = await self._execute_copy_signal(sig)
                executed = result.success if result else False
                order_id = result.order_id if result else ""

                if self._bot:
                    await self._bot.send_copy_alert(sig, executed=executed, order_id=order_id)
                else:
                    logger.info(
                        f"Copy signal: {sig.our_side} ${sig.our_size:.2f} "
                        f"executed={executed} order={order_id}"
                    )
            except Exception as e:
                logger.error(f"Copy signal execution error: {e}")
                if self._bot:
                    await self._bot.send_error_alert(str(e), context="Copy trade execution")

    async def _execute_copy_signal(self, signal):
        """Place order for a copy trade signal."""
        if not self._clob:
            return None

        trade = signal.source_trade
        token_id = _condition_to_token(trade.condition_id, trade.outcome)

        if signal.our_side == "SELL":
            # Exit: sell entire mirrored position — size=0.0 means full close
            # For paper mode, we approximate with the original entry size
            size = signal.our_size if signal.our_size > 0 else 10.0
        else:
            size = signal.our_size

        if size < 1.0:
            logger.debug(f"Copy signal size ${size:.2f} below minimum — skipping")
            return None

        return await self._clob.place_limit_order(
            token_id=token_id,
            side=signal.our_side,
            price=signal.market_price,
            size=size,
        )

    # =========================================================================
    # Mode switch (called by Telegram /mode)
    # =========================================================================

    async def on_mode_switch(self, new_mode: str) -> None:
        """Runtime mode switch — updates CLOB client mode."""
        settings.TRADING_MODE = new_mode
        if self._clob:
            self._clob.mode = new_mode
        logger.info(f"Trading mode switched to: {new_mode.upper()}")

    # =========================================================================
    # Pause / resume (called by Telegram /pause /resume)
    # =========================================================================

    async def _on_pause(self) -> None:
        from backend.core.scheduler import stop_scheduler
        stop_scheduler()
        logger.info("Trading paused via Telegram")

    async def _on_resume(self) -> None:
        from backend.core.scheduler import start_scheduler
        start_scheduler()
        logger.info("Trading resumed via Telegram")


# =========================================================================
# Helpers
# =========================================================================

async def _auto_execute_weather(signals: list, clob: Optional[PolymarketCLOB]) -> None:
    """Execute weather signals without Telegram confirmation (simulation only)."""
    if not clob:
        return
    for sig in signals:
        try:
            market = sig.market
            token_id = getattr(market, "token_id", "") or market.market_id
            price = market.yes_price if sig.direction == "yes" else market.no_price
            result = await clob.place_limit_order(
                token_id=token_id,
                side="BUY",
                price=price,
                size=sig.suggested_size,
            )
            logger.info(
                f"[AUTO-SIM] Weather trade: {sig.market.city_name} "
                f"{sig.direction.upper()} ${sig.suggested_size:.2f} "
                f"order={result.order_id}"
            )
        except Exception as e:
            logger.warning(f"Auto-execute failed: {e}")


from functools import lru_cache as _lru_cache

@_lru_cache(maxsize=1024)
def _condition_to_token(condition_id: str, outcome: str) -> str:
    """
    Map condition_id + outcome to a CLOB token ID via Gamma API.
    Cached — the mapping is immutable (condition_id to token_id never changes).
    outcome: "YES" or "NO"
    """
    import httpx as _httpx
    try:
        resp = _httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={"conditionId": condition_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            logger.warning(f"No market found for condition_id={condition_id}, using fallback")
            return condition_id

        market = data[0]
        tokens = market.get("tokens", [])
        # tokens[0] = YES token, tokens[1] = NO token
        if outcome.upper() == "YES" and len(tokens) > 0:
            return str(tokens[0].get("token_id", condition_id))
        elif outcome.upper() == "NO" and len(tokens) > 1:
            return str(tokens[1].get("token_id", condition_id))

        return condition_id
    except Exception as e:
        logger.warning(f"Failed to resolve token_id for {condition_id}/{outcome}: {e}")
        return condition_id


# =========================================================================
# Entry point
# =========================================================================

async def main() -> None:
    """Run the orchestrator until interrupted."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    orchestrator = Orchestrator()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await orchestrator.start()

    logger.info("PolyEdge running. Press Ctrl+C to stop.")
    await stop_event.wait()

    await orchestrator.stop()
    logger.info("PolyEdge stopped.")


if __name__ == "__main__":
    asyncio.run(main())
