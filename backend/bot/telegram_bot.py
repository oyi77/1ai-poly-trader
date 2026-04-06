"""
PolyEdge Telegram Bot.

Provides:
- Signal alerts: weather (with COPY/SKIP keyboard) and copy trade (notify-only)
- Commands: /status /positions /leaderboard /pause /resume /settings /mode
- Admin-only guard for destructive commands
- Error alerting: unhandled exceptions forwarded to admin

Execution modes:
- Weather signals: sends alert with inline keyboard [COPY TRADE][SKIP][VIEW MARKET]
  User must press COPY TRADE to execute (confirm mode)
- Copy trade signals: auto-executes within risk limits, sends notification after
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

logger = logging.getLogger("trading_bot")

try:
    from telegram import (
        Bot,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
    )
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
    )
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed — Telegram alerts disabled")


class PolyEdgeBot:
    """
    Telegram bot for PolyEdge.

    Usage:
        bot = PolyEdgeBot(token="...", admin_ids=[123456])
        await bot.start()
        await bot.send_weather_signal(signal)  # sends alert with keyboard
        await bot.send_copy_alert(signal)      # sends post-execution notify
        await bot.stop()
    """

    def __init__(
        self,
        token: str,
        admin_ids: list[int],
        on_copy_trade: Optional[Callable] = None,  # called when user presses COPY TRADE
        on_pause: Optional[Callable] = None,
        on_resume: Optional[Callable] = None,
        on_mode_switch: Optional[Callable] = None,
    ):
        self.token = token
        self.admin_ids = set(admin_ids)
        self.on_copy_trade = on_copy_trade
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_mode_switch = on_mode_switch

        self._app: Optional["Application"] = None
        self._bot: Optional["Bot"] = None
        self._paused = False

        # Pending weather signals awaiting user confirmation
        # key: signal_id (condition_id), value: signal data dict
        self._pending_signals: dict[str, dict] = {}

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Initialize and start the bot (non-blocking — runs in background task)."""
        if not TELEGRAM_AVAILABLE:
            logger.warning("Telegram bot disabled — python-telegram-bot not installed")
            return

        if not self.token or self.token == "disabled":
            logger.info("Telegram bot token not configured — alerts disabled")
            return

        self._app = Application.builder().token(self.token).build()
        self._bot = self._app.bot

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("leaderboard", self._cmd_leaderboard))
        self._app.add_handler(CommandHandler("pause", self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("settings", self._cmd_settings))
        self._app.add_handler(CommandHandler("mode", self._cmd_mode))
        self._app.add_handler(CommandHandler("calibration", self._cmd_calibration))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))

        # Start polling in background
        await self._app.initialize()
        await self._app.start()
        asyncio.create_task(self._app.updater.start_polling(drop_pending_updates=True))
        logger.info(f"Telegram bot started — admins: {self.admin_ids}")

    async def stop(self):
        """Graceful shutdown."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    def _is_admin(self, update: "Update") -> bool:
        if not self.admin_ids:
            return True  # No restriction if no admin IDs configured
        return update.effective_user.id in self.admin_ids

    async def _send(self, chat_id: int, text: str, reply_markup=None, parse_mode=None):
        """Safe send with error logging."""
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode or ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def alert_all_admins(self, text: str, reply_markup=None):
        """Send a message to all admin chat IDs."""
        for cid in self.admin_ids:
            await self._send(cid, text, reply_markup=reply_markup)

    # =========================================================================
    # Signal Alerts
    # =========================================================================

    async def send_weather_signal(self, signal) -> None:
        """
        Send a weather signal alert with inline keyboard.
        Signal must have: market, edge, model_probability, market_probability,
        suggested_size, reasoning, ensemble_mean, ensemble_std, ensemble_members
        """
        if not self._bot or self._paused:
            return

        market = signal.market
        condition_id = market.market_id

        # Store pending signal for callback
        self._pending_signals[condition_id] = {
            "signal": signal,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

        edge_pct = abs(signal.edge) * 100
        direction = signal.direction.upper()
        entry_price = market.yes_price if direction == "YES" else market.no_price

        text = (
            f"<b>WEATHER SIGNAL</b>\n"
            f"\n"
            f"<b>{market.city_name}</b> — {market.metric.title()} Temp\n"
            f"<i>{market.title[:60]}</i>\n"
            f"\n"
            f"Side:     <b>{direction}</b> @ {entry_price:.2f}\n"
            f"Model:    {signal.model_probability:.0%}  "
            f"(ensemble {signal.ensemble_mean:.1f}°F ±{signal.ensemble_std:.1f}°F, "
            f"{signal.ensemble_members}m)\n"
            f"Market:   {signal.market_probability:.0%}\n"
            f"<b>Edge:     +{edge_pct:.1f}%</b>\n"
            f"Size:     <b>${signal.suggested_size:.2f}</b>\n"
            f"\n"
            f"Expires: {market.target_date}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ COPY TRADE", callback_data=f"copy:{condition_id}"),
                InlineKeyboardButton("❌ SKIP", callback_data=f"skip:{condition_id}"),
            ],
            [
                InlineKeyboardButton(
                    "📊 View Market",
                    url=f"https://polymarket.com/event/{market.slug or condition_id}"
                ),
            ],
        ])

        await self.alert_all_admins(text, reply_markup=keyboard)

    async def send_copy_alert(self, signal, executed: bool = True, order_id: str = "") -> None:
        """
        Send a post-execution copy trade notification (no keyboard — already executed).
        """
        if not self._bot:
            return

        trade = signal.source_trade
        status = "✅ EXECUTED" if executed else "⚠️ FAILED"
        action = "EXIT" if signal.our_side == "SELL" else "COPY"

        text = (
            f"<b>{action} TRADE — {status}</b>\n"
            f"\n"
            f"Trader: <b>{signal.source_wallet[:10]}...</b> "
            f"(score {signal.trader_score:.0f})\n"
            f"Market: <i>{trade.title[:50]}</i>\n"
            f"\n"
            f"Side:   <b>{signal.our_side} {signal.our_outcome}</b>\n"
            f"Price:  {signal.market_price:.3f}\n"
            f"Size:   <b>${signal.our_size:.2f}</b>\n"
            + (f"Order:  <code>{order_id}</code>\n" if order_id else "")
            + f"\n<i>{signal.reasoning[:120]}</i>"
        )

        await self.alert_all_admins(text)

    async def send_error_alert(self, error: str, context: str = "") -> None:
        """Send an error alert to admins."""
        if not self._bot:
            return
        text = (
            f"<b>⚠️ POLYEDGE ERROR</b>\n"
            f"\n"
            f"{context + chr(10) if context else ''}"
            f"<code>{error[:300]}</code>"
        )
        await self.alert_all_admins(text)

    # =========================================================================
    # Callback handler (inline keyboard buttons)
    # =========================================================================

    async def _handle_callback(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        query = update.callback_query
        await query.answer()

        if not self._is_admin(update):
            await query.edit_message_text("❌ Not authorized.")
            return

        data = query.data
        if data.startswith("copy:"):
            condition_id = data[5:]
            pending = self._pending_signals.pop(condition_id, None)
            if not pending:
                await query.edit_message_text("⚠️ Signal expired or already acted on.")
                return

            signal = pending["signal"]
            if self.on_copy_trade:
                try:
                    result = await self.on_copy_trade(signal)
                    order_id = getattr(result, "order_id", "")
                    await query.edit_message_text(
                        f"✅ Trade executed!\n"
                        f"Size: ${signal.suggested_size:.2f} | "
                        f"Order: {order_id or 'paper'}"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Execution failed: {e}")
            else:
                await query.edit_message_text("✅ Signal acknowledged (no executor configured).")

        elif data.startswith("skip:"):
            condition_id = data[5:]
            self._pending_signals.pop(condition_id, None)
            await query.edit_message_text("❌ Signal skipped.")

    # =========================================================================
    # Command handlers
    # =========================================================================

    async def _cmd_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        status = "🟢 RUNNING" if not self._paused else "⏸ PAUSED"
        await update.message.reply_text(
            f"<b>PolyEdge Bot</b> {status}\n\n"
            f"Commands:\n"
            f"/status — system status\n"
            f"/positions — open positions\n"
            f"/leaderboard — tracked traders\n"
            f"/pause — pause scanning\n"
            f"/resume — resume scanning\n"
            f"/settings — current config\n"
            f"/calibration — weather calibration report\n"
            f"/mode paper|testnet|live — switch mode (admin)",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_status(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        from backend.config import settings
        mode_emoji = {"paper": "🟠 PAPER", "testnet": "🟡 TESTNET", "live": "🔴 LIVE"}
        mode = mode_emoji.get(settings.TRADING_MODE, "🟠 PAPER")
        paused = "⏸ PAUSED" if self._paused else "🟢 RUNNING"
        await update.message.reply_text(
            f"<b>PolyEdge Status</b>\n\n"
            f"Mode:     {mode}\n"
            f"Scanner:  {paused}\n"
            f"Bankroll: ${settings.INITIAL_BANKROLL:,.2f}\n"
            f"Cities:   {settings.WEATHER_CITIES}\n"
            f"Edge min: {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%}",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_positions(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        try:
            from backend.models.database import SessionLocal, Trade
            db = SessionLocal()
            pending = db.query(Trade).filter(Trade.settled == False).order_by(Trade.timestamp.desc()).all()
            db.close()

            if not pending:
                await update.message.reply_text(
                    "📊 <b>Open Positions</b>\n\nNo open positions.",
                    parse_mode=ParseMode.HTML,
                )
                return

            lines = ["📊 <b>Open Positions</b>\n"]
            total_size = 0.0
            for t in pending[:15]:
                mode_tag = f"[{(getattr(t, 'trading_mode', None) or 'paper').upper()[:1]}]"
                lines.append(
                    f"{mode_tag} <b>{t.direction.upper()}</b> {t.market_type} "
                    f"${t.size:.0f} @ {t.entry_price:.0%} "
                    f"<i>{t.market_ticker[:20]}</i>"
                )
                total_size += t.size

            if len(pending) > 15:
                lines.append(f"\n... and {len(pending) - 15} more")

            lines.append(f"\n<b>Total exposure: ${total_size:.0f}</b> across {len(pending)} positions")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(f"Error loading positions: {e}")

    async def _cmd_leaderboard(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        await update.message.reply_text(
            "🏆 <b>Leaderboard</b>\n\n"
            "Copy trader leaderboard data loads on next poll cycle.\n"
            "Use /status to check scanner state.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_pause(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        if not self._is_admin(update):
            await update.message.reply_text("❌ Admin only.")
            return
        self._paused = True
        if self.on_pause:
            await self.on_pause()
        await update.message.reply_text("⏸ Scanning paused. Use /resume to restart.")

    async def _cmd_resume(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        if not self._is_admin(update):
            await update.message.reply_text("❌ Admin only.")
            return
        self._paused = False
        if self.on_resume:
            await self.on_resume()
        await update.message.reply_text("🟢 Scanning resumed.")

    async def _cmd_settings(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        from backend.config import settings
        await update.message.reply_text(
            f"<b>PolyEdge Settings</b>\n\n"
            f"Trading mode:      {settings.TRADING_MODE}\n"
            f"Kelly fraction:    {settings.KELLY_FRACTION}\n"
            f"Max trade size:    ${settings.WEATHER_MAX_TRADE_SIZE}\n"
            f"Edge threshold:    {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%}\n"
            f"Max entry price:   {settings.WEATHER_MAX_ENTRY_PRICE:.0%}\n"
            f"Scan interval:     {settings.WEATHER_SCAN_INTERVAL_SECONDS}s",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_mode(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        if not self._is_admin(update):
            await update.message.reply_text("❌ Admin only.")
            return
        args = context.args
        if not args or args[0] not in ("paper", "testnet", "live"):
            from backend.config import settings
            current = settings.TRADING_MODE
            await update.message.reply_text(
                f"Current mode: <b>{current.upper()}</b>\n\nUsage: /mode paper|testnet|live",
                parse_mode=ParseMode.HTML,
            )
            return
        new_mode = args[0]
        if self.on_mode_switch:
            await self.on_mode_switch(new_mode)

        mode_emoji = {"paper": "🟠", "testnet": "🟡", "live": "🔴"}
        await update.message.reply_text(
            f"{mode_emoji.get(new_mode, '⚪')} Mode switched to <b>{new_mode.upper()}</b>.\n"
            f"New trades will execute in {new_mode} mode.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_calibration(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        try:
            from backend.core.calibration import get_calibration_report
            report = get_calibration_report()
            await update.message.reply_text(f"<pre>{report}</pre>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")


def bot_from_settings() -> "PolyEdgeBot":
    """Create PolyEdgeBot from app settings."""
    from backend.config import settings

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    raw_ids = getattr(settings, "TELEGRAM_ADMIN_CHAT_IDS", "") or ""
    admin_ids = []
    for part in str(raw_ids).split(","):
        part = part.strip()
        if part.isdigit():
            admin_ids.append(int(part))

    return PolyEdgeBot(token=token, admin_ids=admin_ids)
