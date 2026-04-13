"""PolyEdge top-level orchestrator — wires together CLOB, Telegram, scheduler, and strategies."""

import asyncio
import logging
import signal
from typing import Optional

from cachetools import TTLCache

from backend.config import settings
from backend.data.polymarket_clob import PolymarketCLOB, clob_from_settings

logger = logging.getLogger("trading_bot")


class Orchestrator:
    """Top-level coordinator. Create one per process."""

    def __init__(self):
        self._clob: Optional[PolymarketCLOB] = None
        self._bot = None
        self._copy_trader = None
        self._copy_task: Optional[asyncio.Task] = None
        self._running = False
        self._condition_cache: TTLCache = TTLCache(maxsize=2000, ttl=3600)

    async def start(self) -> None:
        """Start all subsystems."""
        self._running = True
        logger.info("Orchestrator starting...")

        self._clob = clob_from_settings()
        await self._clob.__aenter__()

        if settings.TRADING_MODE == "live":
            logger.info("Live mode: deriving API credentials from private key...")
            creds = await self._clob.create_or_derive_api_creds()
            if not creds:
                raise RuntimeError(
                    "Failed to derive Polymarket API credentials from private key. "
                    "Check POLYMARKET_PRIVATE_KEY in .env."
                )
            logger.info("API credentials derived successfully.")

        if settings.TELEGRAM_BOT_TOKEN:
            from backend.bot.telegram_bot import bot_from_settings

            self._bot = bot_from_settings()
            self._bot.on_copy_trade = self._execute_weather_signal
            self._bot.on_pause = self._on_pause
            self._bot.on_resume = self._on_resume
            self._bot.on_mode_switch = self.on_mode_switch
            await self._bot.start()
            from backend.bot.notifier import set_bot

            set_bot(self._bot)

        from backend.strategies.registry import load_all_strategies
        from backend.models.database import SessionLocal, StrategyConfig
        import json

        load_all_strategies()  # trigger auto-registration

        db = SessionLocal()
        try:
            defaults = [
                (
                    "copy_trader",
                    True,
                    60,
                    {"max_wallets": 20, "min_score": 60.0, "poll_interval": 60},
                ),
                (
                    "weather_emos",
                    False,
                    300,
                    {
                        "min_edge": 0.05,
                        "max_position_usd": 100,
                        "calibration_window_days": 40,
                    },
                ),
                (
                    "kalshi_arb",
                    False,
                    30,
                    {"min_edge": 0.02, "allow_live_execution": False},
                ),
                (
                    "btc_oracle",
                    False,
                    30,
                    {"min_edge": 0.03, "max_minutes_to_resolution": 10},
                ),
                (
                    "btc_5m",
                    False,
                    60,
                    {
                        "WARNING": "Dedicated BTC scan job — controlled by SCAN_INTERVAL_SECONDS setting, not this config."
                    },
                ),
                (
                    "btc_momentum",
                    False,
                    60,
                    {
                        "WARNING": "EXPERIMENTAL — documented -49.5% live ROI. Do not enable without re-validation."
                    },
                ),
                (
                    "general_scanner",
                    False,
                    300,
                    {"min_volume": 50000, "min_edge": 0.05, "max_position_usd": 150},
                ),
                (
                    "bond_scanner",
                    False,
                    180,
                    {"min_price": 0.92, "max_price": 0.98, "max_position_usd": 200},
                ),
                (
                    "realtime_scanner",
                    False,
                    60,
                    {"min_edge": 0.03, "max_position_usd": 100},
                ),
                (
                    "whale_pnl_tracker",
                    False,
                    120,
                    {"min_wallet_pnl": 10000, "max_position_usd": 100},
                ),
                ("market_maker", False, 30, {"spread": 0.02, "max_position_usd": 200}),
            ]
            added = 0
            for name, enabled, interval, params in defaults:
                exists = (
                    db.query(StrategyConfig)
                    .filter(StrategyConfig.strategy_name == name)
                    .first()
                )
                if not exists:
                    db.add(
                        StrategyConfig(
                            strategy_name=name,
                            enabled=enabled,
                            interval_seconds=interval,
                            params=json.dumps(params),
                        )
                    )
                    added += 1
            if added:
                db.commit()
                logger.info(f"Seeded {added} missing strategy configs")
        finally:
            db.close()

        self._copy_trader = None
        self._copy_task = None

        self._patch_weather_job()

        from backend.core.scheduler import start_scheduler

        start_scheduler()

        self._phase2 = init_phase2_modules()
        if self._phase2:
            logger.info(f"Phase 2 modules active: {list(self._phase2.keys())}")

        logger.info("Orchestrator started.")

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("Orchestrator stopping...")
        self._running = False

        if self._bot:
            await self._bot.stop()

        if self._clob:
            if settings.TRADING_MODE == "live":
                await self._clob.cancel_all_orders()
            await self._clob.__aexit__(None, None, None)

        from backend.core.scheduler import stop_scheduler

        stop_scheduler()

        logger.info("Orchestrator stopped.")

    def _patch_weather_job(self) -> None:
        """Replace weather_scan_and_trade_job with a version that dispatches Telegram alerts."""
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

            log_event(
                "data", f"Weather: {len(signals)} signals, {len(actionable)} actionable"
            )

            if not actionable:
                return

            # Telegram confirm-mode: send alert with keyboard, wait for user press
            if bot and bot._bot:
                for signal in actionable[:3]:
                    try:
                        await bot.send_weather_signal(signal)
                        log_event(
                            "info",
                            f"Telegram alert sent: {signal.market.city_name} {signal.direction.upper()}",
                        )
                    except Exception as e:
                        logger.warning(
                            f"[orchestrator.patched_weather_job] {type(e).__name__}: Failed to send weather alert: {e}"
                        )
            else:
                if settings.TRADING_MODE == "paper":
                    await _auto_execute_weather(actionable[:3], clob)

            try:
                await original_job()
            except Exception as e:
                logger.debug(
                    f"[orchestrator.patched_weather_job] {type(e).__name__}: Original weather job error (non-fatal): {e}"
                )

        sched_mod.weather_scan_and_trade_job = patched_weather_job

    async def _execute_weather_signal(self, signal) -> None:
        """Execute a weather signal triggered by Telegram COPY TRADE button."""
        from backend.core.strategy_executor import execute_decision

        market = signal.market
        token_id = getattr(market, "token_id", "") or market.market_id
        price = market.yes_price if signal.direction == "yes" else market.no_price

        decision = {
            "market_ticker": market.market_id,
            "direction": signal.direction,
            "size": signal.suggested_size,
            "entry_price": price,
            "edge": getattr(signal, "edge", 0.0),
            "confidence": getattr(signal, "model_probability", 0.5),
            "model_probability": getattr(signal, "model_probability", 0.5),
            "token_id": token_id,
            "platform": "polymarket",
            "market_type": "weather",
            "reasoning": "weather copy trade",
        }

        result = await execute_decision(decision, "weather_copy", db=None)
        if result is None:
            raise RuntimeError(
                "Weather copy trade rejected by risk manager or duplicate"
            )

        logger.info(
            f"Weather trade executed: {signal.direction} ${signal.suggested_size:.2f} @ {price:.3f}"
        )
        return result

    async def _handle_copy_signals(self, signals: list) -> None:
        for sig in signals:
            try:
                result = await self._execute_copy_signal(sig)
                executed = result.success if result else False
                order_id = result.order_id if result else ""

                if self._bot:
                    await self._bot.send_copy_alert(
                        sig, executed=executed, order_id=order_id
                    )
                else:
                    logger.info(
                        f"Copy signal: {sig.our_side} ${sig.our_size:.2f} "
                        f"executed={executed} order={order_id}"
                    )
            except Exception as e:
                logger.error(
                    f"[orchestrator._handle_copy_signals] {type(e).__name__}: Copy signal execution error: {e}",
                    exc_info=True,
                )
                if self._bot:
                    await self._bot.send_error_alert(
                        str(e), context="Copy trade execution"
                    )

    async def _execute_copy_signal(self, signal):
        if not self._clob:
            return None

        trade = signal.source_trade
        token_id = await self._condition_to_token(trade.condition_id, trade.outcome)

        if signal.our_side == "SELL":
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

    async def on_mode_switch(self, new_mode: str) -> None:
        """Runtime mode switch — updates CLOB client mode."""
        settings.TRADING_MODE = new_mode
        if self._clob:
            self._clob.mode = new_mode
        logger.info(f"Trading mode switched to: {new_mode.upper()}")

    async def _on_pause(self) -> None:
        from backend.core.scheduler import stop_scheduler

        stop_scheduler()
        logger.info("Trading paused via Telegram")

    async def _on_resume(self) -> None:
        from backend.core.scheduler import start_scheduler

        start_scheduler()
        logger.info("Trading resumed via Telegram")

    async def _condition_to_token(self, condition_id: str, outcome: str) -> str:
        """Map condition_id + outcome ("YES"/"NO") to a CLOB token ID via Gamma API."""
        cache_key = f"{condition_id}:{outcome}"
        if cache_key in self._condition_cache:
            return self._condition_cache[cache_key]

        import httpx as _httpx

        try:
            async with _httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"conditionId": condition_id},
                    timeout=10.0,
                )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                logger.warning(
                    f"No market found for condition_id={condition_id}, using fallback"
                )
                result = condition_id
                self._condition_cache[cache_key] = result
                return result

            market = data[0]
            tokens = market.get("tokens", [])
            if outcome.upper() == "YES" and len(tokens) > 0:
                result = str(tokens[0].get("token_id", condition_id))
            elif outcome.upper() == "NO" and len(tokens) > 1:
                result = str(tokens[1].get("token_id", condition_id))
            else:
                result = condition_id

            self._condition_cache[cache_key] = result
            return result
        except (httpx.HTTPError, KeyError, IndexError) as e:
            logger.warning(
                f"[orchestrator._condition_to_token] {type(e).__name__}: Failed to resolve token_id for {condition_id}/{outcome}: {e}"
            )
            return condition_id


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
            logger.warning(
                f"[orchestrator._auto_execute_weather] {type(e).__name__}: Auto-execute failed: {e}"
            )


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


def init_phase2_modules() -> dict:
    """Initialize Phase 2 modules based on feature flags. Returns dict of active instances."""
    from backend.config import settings

    active: dict = {}

    if getattr(settings, "WHALE_LISTENER_ENABLED", False):
        try:
            from backend.data.polygon_listener import PolygonListener

            active["whale_listener"] = PolygonListener()
        except Exception as e:
            logger.warning(
                f"[orchestrator.init_phase2] {type(e).__name__}: PolygonListener init failed: {e}"
            )

    if getattr(settings, "NEWS_FEED_ENABLED", False):
        try:
            from backend.data.feed_aggregator import FeedAggregator

            active["news_feed"] = FeedAggregator()
        except Exception as e:
            logger.warning(
                f"[orchestrator.init_phase2] {type(e).__name__}: FeedAggregator init failed: {e}"
            )

    if getattr(settings, "AUTO_TRADER_ENABLED", False):
        try:
            from backend.core.auto_trader import AutoTrader
            from backend.core.risk_manager import RiskManager

            active["auto_trader"] = AutoTrader(RiskManager())
        except Exception as e:
            logger.warning(
                f"[orchestrator.init_phase2] {type(e).__name__}: AutoTrader init failed: {e}"
            )

    if getattr(settings, "ARBITRAGE_DETECTOR_ENABLED", False):
        try:
            from backend.core.arbitrage_detector import ArbitrageDetector

            active["arbitrage"] = ArbitrageDetector()
        except Exception as e:
            logger.warning(
                f"[orchestrator.init_phase2] {type(e).__name__}: ArbitrageDetector init failed: {e}"
            )

    if getattr(settings, "AGI_PIPELINE_ENABLED", False):
        try:
            from backend.research.pipeline import AutonomousResearchPipeline
            import asyncio as _asyncio

            _research = AutonomousResearchPipeline()
            _asyncio.ensure_future(_research.run_continuous())
            active["agi_research"] = _research
        except Exception as e:
            logger.warning(
                f"[orchestrator.init_phase2] {type(e).__name__}: AGI research pipeline init failed: {e}"
            )

    return active


if __name__ == "__main__":
    asyncio.run(main())
