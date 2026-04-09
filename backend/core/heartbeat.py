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


def update_heartbeat(db, strategy_name: str) -> None:
    """Update the heartbeat timestamp for a strategy. Called after each cycle."""
    try:
        state = db.query(BotState).first()
        if not state:
            return
        data = {}
        if state.misc_data:
            try:
                data = json.loads(state.misc_data) if isinstance(state.misc_data, str) else dict(state.misc_data)
            except Exception:
                logger.warning("Failed to parse misc_data JSON, resetting")
                data = {}
        data[f"{HEARTBEAT_PREFIX}{strategy_name}"] = datetime.now(timezone.utc).isoformat()
        state.misc_data = json.dumps(data)
        db.commit()
    except Exception as e:
        logger.debug(f"update_heartbeat failed for {strategy_name}: {e}")


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
                data = json.loads(state.misc_data) if isinstance(state.misc_data, str) else {}
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
                    logger.warning(f"Failed to check heartbeat for strategy {name}")

            result.append({
                "name": cfg.strategy_name,
                "last_heartbeat": last_hb_str,
                "lag_seconds": round(lag, 1) if lag is not None else None,
                "healthy": healthy,
                "interval_seconds": cfg.interval_seconds or 60,
            })
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
                    f"lag={h['lag_seconds']}s threshold={h['interval_seconds']*2}s",
                    extra={"component": "watchdog"},
                )
                record_decision(
                    db, "watchdog", h["name"], "ERROR",
                    signal_data={"lag_seconds": h["lag_seconds"], "healthy": False},
                    reason=f"Heartbeat stale: {h['lag_seconds']:.0f}s since last cycle"
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
