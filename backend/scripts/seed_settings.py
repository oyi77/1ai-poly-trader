"""Seed initial settings from .env.example defaults."""

import os
from datetime import datetime, timezone
from backend.models.database import SessionLocal, Setting, engine
from sqlalchemy import inspect


DEFAULT_SETTINGS = {
    "TRADING_MODE": ("paper", "Trading mode: paper, testnet, or live"),
    "INITIAL_BANKROLL": ("1000.0", "Starting bankroll in USD"),
    "SIGNAL_APPROVAL_MODE": ("manual", "Signal approval: manual, auto_approve, auto_deny"),
    "TELEGRAM_BOT_TOKEN": ("", "Telegram bot token for alerts"),
    "TELEGRAM_ADMIN_CHAT_IDS": ("", "Comma-separated Telegram chat IDs"),
    "KALSHI_ENABLED": ("false", "Enable Kalshi trading"),
    "AI_PROVIDER": ("groq", "AI provider: groq, claude, omniroute, custom"),
    "GROQ_API_KEY": ("", "Groq API key"),
    "GROQ_MODEL": ("llama-3.1-8b-instant", "Groq model name"),
    "AI_DAILY_BUDGET_USD": ("1.0", "Daily AI budget in USD"),
    "WEBSEARCH_ENABLED": ("true", "Enable web search for market research"),
    "WEBSEARCH_PROVIDER": ("tavily", "Web search provider: tavily, exa, serper, duckduckgo"),
    "WEBSEARCH_FALLBACK_PROVIDER": ("duckduckgo", "Fallback web search provider"),
    "WEBSEARCH_MAX_RESULTS": ("5", "Max web search results per query"),
    "WEBSEARCH_TIMEOUT_SECONDS": ("15.0", "Web search timeout in seconds"),
    "DATABASE_URL": ("sqlite:///./tradingbot.db", "Database connection URL"),
    "WEATHER_ENABLED": ("true", "Enable weather trading strategy"),
    "WEATHER_CITIES": ("nyc,chicago,miami,dallas,seattle", "Comma-separated weather cities"),
    "WEATHER_MIN_EDGE_THRESHOLD": ("0.08", "Minimum edge threshold for weather trades"),
    "WEATHER_MAX_ENTRY_PRICE": ("0.70", "Max entry price for weather markets"),
    "WEATHER_MAX_TRADE_SIZE": ("100.0", "Max trade size for weather markets"),
    "KELLY_FRACTION": ("0.15", "Kelly fraction for position sizing"),
    "DAILY_LOSS_LIMIT": ("300.0", "Daily loss limit in USD"),
    "MAX_TRADE_SIZE": ("75.0", "Max single trade size in USD"),
}


def seed_settings():
    """Seed initial settings from defaults if table is empty."""
    inspector = inspect(engine)
    
    if "settings" not in inspector.get_table_names():
        return False
    
    db = SessionLocal()
    try:
        existing_count = db.query(Setting).count()
        if existing_count > 0:
            return False
        
        now = datetime.now(timezone.utc)
        settings_to_add = []
        
        for key, (value, description) in DEFAULT_SETTINGS.items():
            setting_type = "string"
            if key in ["INITIAL_BANKROLL", "AI_DAILY_BUDGET_USD", "WEATHER_MIN_EDGE_THRESHOLD", 
                       "WEATHER_MAX_ENTRY_PRICE", "WEATHER_MAX_TRADE_SIZE", "KELLY_FRACTION",
                       "DAILY_LOSS_LIMIT", "MAX_TRADE_SIZE", "WEBSEARCH_TIMEOUT_SECONDS"]:
                setting_type = "float"
            elif key in ["WEBSEARCH_MAX_RESULTS"]:
                setting_type = "int"
            elif key in ["KALSHI_ENABLED", "WEBSEARCH_ENABLED", "WEATHER_ENABLED"]:
                setting_type = "bool"
            
            setting = Setting(
                key=key,
                value=value,
                description=description,
                type=setting_type,
                created_at=now,
                updated_at=now,
                updated_by_user_id="system"
            )
            settings_to_add.append(setting)
        
        db.add_all(settings_to_add)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    if seed_settings():
        print(f"Seeded {len(DEFAULT_SETTINGS)} settings")
    else:
        print("Settings already exist or table not found")
