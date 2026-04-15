"""
Heartbeat and watchdog system for PolyEdge.

Every strategy cycle updates a heartbeat row in BotState.
The watchdog job checks all enabled strategies and alerts if any go silent.
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from backend.models.database import SessionLocal, BotState, StrategyConfig

logger = logging.getLogger("trading_bot")

HEARTBEAT_PREFIX = "heartbeat:"
_recent_alerts: dict[str, datetime] = {}  # strategy_name -> last_alert_time
ALERT_DEDUP_WINDOW = timedelta(minutes=5)


def _do_heartbeat_write_raw(strategy_name: str) -> None:
    """Write heartbeat via raw sqlite3 — bypasses SQLAlchemy pool entirely."""
    import sqlite3
    from backend.config import settings

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        row = conn.execute("SELECT misc_data FROM bot_state WHERE id=1").fetchone()
        if not row:
            return
        data = {}
        if row[0]:
            try:
                data = json.loads(row[0])
            except Exception:
                data = {}
        data[f"{HEARTBEAT_PREFIX}{strategy_name}"] = datetime.now(
            timezone.utc
        ).isoformat()
        conn.execute("UPDATE bot_state SET misc_data=? WHERE id=1", (json.dumps(data),))
        conn.commit()
    finally:
        conn.close()


def update_heartbeat(db, strategy_name: str) -> None:
    """Update heartbeat timestamp for a strategy.

    Uses raw sqlite3 to bypass SQLAlchemy pool and avoid pool exhaustion.
    Retries up to 5 times with exponential backoff + jitter.
    """
    import time
    import random

    max_retries = 5
    for attempt in range(max_retries):
        try:
            _do_heartbeat_write_raw(strategy_name)
            return
        except Exception as e:
            if attempt < max_retries - 1:
                base_sleep = 0.3 * (2**attempt)  # 0.3, 0.6, 1.2, 2.4
                jitter = random.uniform(0, base_sleep * 0.5)
                sleep_time = base_sleep + jitter
                logger.warning(
                    f"update_heartbeat attempt {attempt + 1} failed for "
                    f"{strategy_name}: {e} — retrying in {sleep_time:.1f}s"
                )
                time.sleep(sleep_time)
            else:
                logger.error(
                    f"update_heartbeat failed for {strategy_name} after "
                    f"{max_retries} attempts: {e}"
                )


def get_strategy_health(db) -> list[dict]:
    """
    Return health status for all enabled strategies.
    Each entry: {name, last_heartbeat, lag_seconds, healthy}
    """
    result = []
    try:
        configs = db.query(StrategyConfig).filter(StrategyConfig.enabled == True).all()
        state = db.query(BotState).first()
        data = {}
        if state and state.misc_data:
            try:
                data = (
                    json.loads(state.misc_data)
                    if isinstance(state.misc_data, str)
                    else {}
                )
            except Exception:
                logger.warning("Failed to parse misc_data JSON, resetting")
                data = {}

        now = datetime.now(timezone.utc)
        for cfg in configs:
            key = f"{HEARTBEAT_PREFIX}{cfg.strategy_name}"
            last_hb_str = data.get(key)
            last_hb = None
            lag = None
            healthy = False
            if last_hb_str:
                try:
                    last_hb = datetime.fromisoformat(last_hb_str)
                    if last_hb.tzinfo is None:
                        last_hb = last_hb.replace(tzinfo=timezone.utc)
                    lag = (now - last_hb).total_seconds()
                    # healthy = heartbeat within 2x the strategy interval
                    threshold = (cfg.interval_seconds or 60) * 2
                    healthy = lag < threshold
                except Exception:
                    logger.warning(
                        f"Failed to check heartbeat for strategy {cfg.strategy_name}"
                    )

            result.append(
                {
                    "name": cfg.strategy_name,
                    "last_heartbeat": last_hb_str,
                    "lag_seconds": round(lag, 1) if lag is not None else None,
                    "healthy": healthy,
                    "interval_seconds": cfg.interval_seconds or 60,
                }
            )
    except Exception as e:
        logger.error(f"get_strategy_health failed: {e}")
    return result


async def watchdog_job() -> None:
    """
    APScheduler watchdog job — runs every 30s.
    Checks strategy heartbeats and fires alerts for stale ones.
    """
    from backend.core.decisions import record_decision

    db = SessionLocal()
    try:
        healths = get_strategy_health(db)
        for h in healths:
            if not h["healthy"] and h["lag_seconds"] is not None:
                logger.error(
                    f"[WATCHDOG] Strategy {h['name']} heartbeat stale: "
                    f"lag={h['lag_seconds']}s threshold={h['interval_seconds'] * 2}s",
                    extra={"component": "watchdog"},
                )
                record_decision(
                    db,
                    "watchdog",
                    h["name"],
                    "ERROR",
                    signal_data={"lag_seconds": h["lag_seconds"], "healthy": False},
                    reason=f"Heartbeat stale: {h['lag_seconds']:.0f}s since last cycle",
                )
                db.commit()

                # Send Telegram alert if configured (with dedup window)
                try:
                    from backend.config import settings

                    if settings.TELEGRAM_BOT_TOKEN:
                        last_alert = _recent_alerts.get(h["name"])
                        now_dt = datetime.now(timezone.utc)
                        if last_alert and (now_dt - last_alert) < ALERT_DEDUP_WINDOW:
                            continue  # skip duplicate alert within 5 min window
                        _recent_alerts[h["name"]] = now_dt
                        _send_telegram_alert_sync(
                            f"⚠️ WATCHDOG: Strategy {h['name']} is silent "
                            f"({h['lag_seconds']:.0f}s since last heartbeat)"
                        )
                except Exception as te:
                    logger.debug(f"Watchdog Telegram alert failed: {te}")
    finally:
        db.close()


def _send_telegram_alert_sync(message: str) -> None:
    """Fire-and-forget Telegram message (sync, for watchdog use)."""
    import httpx
    from backend.config import settings

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return
    admin_ids = getattr(settings, "TELEGRAM_ADMIN_CHAT_IDS", "")
    for chat_id in str(admin_ids).split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=5.0,
            )
        except Exception:
            logger.warning("Failed to send Telegram heartbeat alert")


async def wallet_sync_job() -> None:
    """
    APScheduler job — fetches live CLOB wallet balance and persists to bot_state.
    Runs every 60s to keep the dashboard bankroll in sync with on-chain reality.
    """
    from backend.config import settings

    if settings.TRADING_MODE not in ("live", "testnet"):
        return

    try:
        from backend.data.polymarket_clob import clob_from_settings

        clob = clob_from_settings()
        async with clob:
            await clob.create_or_derive_api_creds()
            balance_data = await clob.get_wallet_balance()
            usdc_balance = balance_data.get("usdc_balance", 0.0)
            error = balance_data.get("error")

            if usdc_balance >= 0 and not error:
                _sync_balance_to_db(usdc_balance, settings.TRADING_MODE)
                logger.info(
                    f"wallet_sync: {settings.TRADING_MODE} balance = ${usdc_balance:.2f}"
                )
    except Exception as e:
        logger.warning(f"wallet_sync_job failed: {e}")


def _sync_balance_to_db(balance: float, mode: str) -> None:
    """Write wallet balance to bot_state DB row (raw sqlite3 to bypass pool)."""
    import sqlite3
    from backend.config import settings

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        if mode == "live":
            conn.execute("UPDATE bot_state SET bankroll=? WHERE id=1", (balance,))
        elif mode == "testnet":
            conn.execute(
                "UPDATE bot_state SET testnet_bankroll=? WHERE id=1", (balance,)
            )
        conn.commit()
        logger.debug(f"wallet_sync: {mode} balance updated to ${balance:.2f}")
    finally:
        conn.close()
