"""Configuration settings for the BTC 5-min trading bot."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (SQLite for Phase 1, PostgreSQL for production)
    DATABASE_URL: str = "sqlite:///./tradingbot.db"

    # API Keys (optional)
    POLYMARKET_API_KEY: Optional[str] = None

    # Polymarket auth (for live trading)
    POLYMARKET_PRIVATE_KEY: Optional[str] = None
    POLYMARKET_API_SECRET: Optional[str] = None
    POLYMARKET_API_PASSPHRASE: Optional[str] = None

    # Kalshi API
    KALSHI_API_KEY_ID: Optional[str] = None
    KALSHI_PRIVATE_KEY_PATH: Optional[str] = None
    KALSHI_ENABLED: bool = True

    # AI API Keys
    GROQ_API_KEY: Optional[str] = None

    # AI Model Configuration
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # AI Provider Selection: groq, claude, omniroute, custom
    AI_PROVIDER: str = "groq"

    # Custom / OmniRoute provider settings (OpenAI-compatible API)
    AI_BASE_URL: Optional[str] = None   # e.g. https://api.omniroute.ai/v1
    AI_MODEL: Optional[str] = None      # overrides provider default
    AI_API_KEY: Optional[str] = None    # API key for custom/omniroute providers

    # AI Feature Flags
    AI_LOG_ALL_CALLS: bool = True
    AI_DAILY_BUDGET_USD: float = 1.0

    # Trading mode: "paper", "testnet", or "live"
    TRADING_MODE: str = "paper"

    # Testnet / network config
    POLYGON_AMOY_RPC: str = "https://rpc-amoy.polygon.technology"
    POLYGON_AMOY_CHAIN_ID: int = 80002
    POLYMARKET_TESTNET_CLOB_HOST: str = "https://clob.polymarket.com"

    # Bot settings - BTC 5-MIN TRADING
    INITIAL_BANKROLL: float = 100.0
    KELLY_FRACTION: float = 0.15  # Fractional Kelly

    # BTC 5-min specific settings
    SCAN_INTERVAL_SECONDS: int = 60  # Scan every minute
    SETTLEMENT_INTERVAL_SECONDS: int = 120  # Check settlements every 2 min
    BTC_PRICE_SOURCE: str = "coinbase"
    MIN_EDGE_THRESHOLD: float = 0.02  # 2% edge required — these are 50/50 markets
    MAX_ENTRY_PRICE: float = 0.55  # Enter up to 55c
    MAX_TRADES_PER_WINDOW: int = 1
    MAX_TOTAL_PENDING_TRADES: int = 20

    # Risk management
    DAILY_LOSS_LIMIT: float = 300.0
    MAX_TRADE_SIZE: float = 75.0
    MIN_TIME_REMAINING: int = 60  # Don't trade windows closing in < 60s
    MAX_TIME_REMAINING: int = 1800  # Trade windows up to 30min out

    # Indicator weights for composite signal (must sum to ~1.0)
    WEIGHT_RSI: float = 0.20
    WEIGHT_MOMENTUM: float = 0.35
    WEIGHT_VWAP: float = 0.20
    WEIGHT_SMA: float = 0.15
    WEIGHT_MARKET_SKEW: float = 0.10

    # Volume filter
    MIN_MARKET_VOLUME: float = 100.0  # Low volume for 5-min markets

    # Weather trading settings
    WEATHER_ENABLED: bool = True
    WEATHER_SCAN_INTERVAL_SECONDS: int = 300  # 5 min
    WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800  # 30 min
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.08  # 8% — weather has more signal than 5-min BTC
    WEATHER_MAX_ENTRY_PRICE: float = 0.70
    WEATHER_MAX_TRADE_SIZE: float = 100.0
    WEATHER_CITIES: str = "nyc,chicago,miami,dallas,seattle,atlanta,los_angeles,denver,london,seoul,tokyo"

    # Admin API security
    ADMIN_API_KEY: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"

    # Telegram bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_CHAT_IDS: str = ""  # comma-separated chat IDs

    # Polygon blockchain listener
    POLYGON_WS_URL: str = "wss://polygon-rpc.com"
    CONDITIONAL_TOKENS_ADDRESS: str = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    MIN_WHALE_TRADE_USD: float = 1000.0
    WHALE_LISTENER_ENABLED: bool = False

    # Job Queue Settings
    JOB_WORKER_ENABLED: bool = False  # Phase 1: disabled by default
    JOB_QUEUE_URL: str = "sqlite:///./job_queue.db"  # or "redis://localhost:6379"
    JOB_TIMEOUT_SECONDS: int = 300  # 5 minutes
    MAX_CONCURRENT_JOBS: int = 1
    DB_EXECUTOR_MAX_WORKERS: int = 4

    MAX_POSITION_FRACTION: float = 0.05
    MAX_TOTAL_EXPOSURE_FRACTION: float = 0.50
    SLIPPAGE_TOLERANCE: float = 0.02
    DAILY_DRAWDOWN_LIMIT_PCT: float = 0.10  # Pause trading if 24h loss > 10% of bankroll
    WEEKLY_DRAWDOWN_LIMIT_PCT: float = 0.20  # Pause trading if 7d loss > 20% of bankroll

    AUTO_APPROVE_MIN_CONFIDENCE: float = 0.85
    AUTO_TRADER_ENABLED: bool = False

    # Signal approval mode: "manual", "auto_approve", "auto_deny"
    # manual: always show popup for user approval
    # auto_approve: auto-approve signals above AUTO_APPROVE_MIN_CONFIDENCE
    # auto_deny: auto-deny all signals
    SIGNAL_APPROVAL_MODE: str = "manual"

    # Signal notification duration (milliseconds)
    SIGNAL_NOTIFICATION_DURATION_MS: int = 10000

    # Phase 2 feature flags
    NEWS_FEED_ENABLED: bool = False
    ARBITRAGE_DETECTOR_ENABLED: bool = False
    NEWS_FEED_INTERVAL_SECONDS: int = 600
    ARBITRAGE_SCAN_INTERVAL_SECONDS: int = 120

    # Cache Settings
    CACHE_URL: str = "sqlite:///./cache.db"  # or "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    @property
    def SIMULATION_MODE(self) -> bool:
        """Backward-compat property — True for paper and testnet, False only for live."""
        return self.TRADING_MODE != "live"

    class Config:
        env_file = ".env"


settings = Settings()
