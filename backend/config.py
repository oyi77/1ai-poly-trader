"""Configuration settings for the BTC 5-min trading bot."""

from pydantic import model_validator
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
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
    POLYMARKET_SIGNATURE_TYPE: int = 0  # 0=EOA, 1=Poly-Proxy (email login), 2=Poly-EOA

    # Polymarket Builder Program credentials (for testnet/live gasless trading)
    POLYMARKET_BUILDER_API_KEY: Optional[str] = None
    POLYMARKET_BUILDER_SECRET: Optional[str] = None
    POLYMARKET_BUILDER_PASSPHRASE: Optional[str] = None
    POLYMARKET_BUILDER_ADDRESS: Optional[str] = (
        None  # Builder proxy address (funder for CLOB orders)
    )

    # Polymarket Relayer API (gasless on-chain operations)
    POLYMARKET_RELAYER_API_KEY: Optional[str] = None
    POLYMARKET_RELAYER_API_KEY_ADDRESS: Optional[str] = None

    # Kalshi API
    KALSHI_API_KEY_ID: Optional[str] = None
    KALSHI_PRIVATE_KEY_PATH: Optional[str] = None
    KALSHI_ENABLED: bool = False

    # AI API Keys
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # AI Model Configuration
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # AI Provider Selection: groq, claude, omniroute, custom
    AI_PROVIDER: str = "groq"

    # LLM Router — role-based provider routing
    LLM_DEFAULT_PROVIDER: str = "groq"
    LLM_DEBATE_PROVIDER: str = "groq"
    LLM_JUDGE_PROVIDER: str = "groq"

    # Custom / OmniRoute provider settings (OpenAI-compatible API)
    AI_BASE_URL: Optional[str] = None  # e.g. https://api.omniroute.ai/v1
    AI_MODEL: Optional[str] = None  # overrides provider default
    AI_API_KEY: Optional[str] = None  # API key for custom/omniroute providers

    # AI Feature Flags
    AI_ENABLED: bool = False  # Master toggle for AI-enhanced signals
    AI_LOG_ALL_CALLS: bool = True
    AI_DAILY_BUDGET_USD: float = 1.0
    AI_SIGNAL_WEIGHT: float = 0.30  # Weight of AI in ensemble (0 = disabled, max 0.50)

    # Debate engine gate — only invoke Bull/Bear/Judge debate when initial
    # single-pass edge exceeds this threshold.  Lower values mean more debates
    # (more LLM calls, better accuracy); higher values skip debate for
    # borderline signals and save tokens.
    MIN_DEBATE_EDGE: float = 0.04

    # Trading mode: "paper", "testnet", or "live"
    TRADING_MODE: str = "paper"

    # Testnet / network config
    POLYGON_AMOY_RPC: str = "https://rpc-amoy.polygon.technology"
    POLYGON_AMOY_CHAIN_ID: int = 80002

    # Bot settings - BTC 5-MIN TRADING
    INITIAL_BANKROLL: float = 100.0
    KELLY_FRACTION: float = (
        0.05  # Ultra-conservative fractional Kelly for $100 bankroll
    )

    # BTC 5-min specific settings
    SCAN_INTERVAL_SECONDS: int = 60  # Scan every minute
    SETTLEMENT_INTERVAL_SECONDS: int = 120  # Check settlements every 2 min
    BTC_PRICE_SOURCE: str = "coinbase"
    MIN_EDGE_THRESHOLD: float = (
        0.05  # 5% edge required — lower threshold to find more opportunities
    )
    MAX_ENTRY_PRICE: float = 0.80  # Allow entries up to 80c for bond-like trades
    MAX_TRADES_PER_WINDOW: int = 2
    MAX_TOTAL_PENDING_TRADES: int = 12
    STALE_TRADE_HOURS: int = 48

    # Risk management — tuned for $100 bankroll
    DAILY_LOSS_LIMIT: float = 5.0
    MAX_TRADE_SIZE: float = 8.0
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
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.10  # 10% — weather has more signal
    WEATHER_MAX_ENTRY_PRICE: float = 0.70
    WEATHER_MAX_TRADE_SIZE: float = 10.0
    WEATHER_CITIES: str = (
        "nyc,chicago,miami,dallas,seattle,atlanta,los_angeles,denver,london,seoul,tokyo"
    )

    # Data aggregator staleness guard (seconds; None = unlimited)
    DATA_AGGREGATOR_MAX_STALE_AGE: float = 300.0

    # Admin API security
    ADMIN_API_KEY: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"

    # Telegram bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_CHAT_IDS: str = ""  # comma-separated chat IDs
    TELEGRAM_HIGH_CONFIDENCE_ALERTS: bool = (
        True  # Send alerts for high-confidence signals (>=75%)
    )

    # Polygon blockchain listener
    POLYGON_WS_URL: str = "wss://polygon-rpc.com"
    CONDITIONAL_TOKENS_ADDRESS: str = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    MIN_WHALE_TRADE_USD: float = 1000.0
    WHALE_LISTENER_ENABLED: bool = False

    # Polymarket WebSocket (real-time market data)
    POLYMARKET_WS_ENABLED: bool = True
    POLYMARKET_USER_WS_ENABLED: bool = False

    # Job Queue Settings
    JOB_WORKER_ENABLED: bool = False  # Phase 1: disabled by default
    JOB_QUEUE_URL: str = "sqlite:///./job_queue.db"  # or "redis://localhost:6379"
    JOB_TIMEOUT_SECONDS: int = 300  # 5 minutes
    MAX_CONCURRENT_JOBS: int = 1
    DB_EXECUTOR_MAX_WORKERS: int = 4

    MAX_POSITION_FRACTION: float = 0.08
    MAX_TOTAL_EXPOSURE_FRACTION: float = 0.70
    SLIPPAGE_TOLERANCE: float = 0.02
    DAILY_DRAWDOWN_LIMIT_PCT: float = (
        0.10  # Pause trading if 24h loss > 10% of bankroll
    )
    WEEKLY_DRAWDOWN_LIMIT_PCT: float = (
        0.20  # Pause trading if 7d loss > 20% of bankroll
    )

    AUTO_APPROVE_MIN_CONFIDENCE: float = 0.55
    AUTO_TRADER_ENABLED: bool = False

    # Signal approval mode: "manual", "auto_approve", "auto_deny"
    # manual: always show popup for user approval
    # auto_approve: auto-approve signals above AUTO_APPROVE_MIN_CONFIDENCE
    # auto_deny: auto-deny all signals
    SIGNAL_APPROVAL_MODE: str = "manual"

    # Signal notification duration (milliseconds)
    SIGNAL_NOTIFICATION_DURATION_MS: int = 10000

    # Auto-improve job (weekly learning from outcomes)
    AUTO_IMPROVE_ENABLED: bool = True
    AUTO_IMPROVE_INTERVAL_DAYS: int = 7  # Run weekly
    AUTO_IMPROVE_TRADE_LIMIT: int = 100  # Analyze last N trades

    # Self-review job (daily attribution, postmortems, degradation detection)
    SELF_REVIEW_ENABLED: bool = True
    SELF_REVIEW_INTERVAL_DAYS: int = 1  # Run daily

    # Research pipeline job (continuous market research)
    RESEARCH_PIPELINE_ENABLED: bool = True
    RESEARCH_PIPELINE_INTERVAL_HOURS: int = 4  # Run every 4 hours

    # Database backup settings
    DB_BACKUP_INTERVAL_HOURS: int = 6  # Run every 6 hours (0 to disable)
    DB_BACKUP_DIR: str = "backups"
    DB_BACKUP_RETENTION_DAYS: int = 30

    # Phase 2 feature flags
    NEWS_FEED_ENABLED: bool = False
    ARBITRAGE_DETECTOR_ENABLED: bool = False
    NEWS_FEED_INTERVAL_SECONDS: int = 600
    ARBITRAGE_SCAN_INTERVAL_SECONDS: int = 120

    # Cache Settings
    CACHE_URL: str = "sqlite:///./cache.db"  # or "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Redis Pub/Sub for WebSocket (multi-instance support)
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_ENABLED: bool = False  # Enable for multi-instance deployments

    # Web Search Provider Settings
    # Primary: "tavily", "crw", "duckduckgo", "exa", "serper"
    # Fallback: "duckduckgo" (free, no API key required)
    WEBSEARCH_PROVIDER: str = "tavily"
    WEBSEARCH_FALLBACK_PROVIDER: str = "duckduckgo"
    WEBSEARCH_ENABLED: bool = True
    TAVILY_API_KEY: Optional[str] = None
    CRW_API_URL: Optional[str] = None  # e.g. https://fastcrw.com/api
    CRW_API_KEY: Optional[str] = None
    EXA_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    WEBSEARCH_MAX_RESULTS: int = 5
    WEBSEARCH_TIMEOUT_SECONDS: float = 15.0

    @model_validator(mode="after")
    def _validate_trading_credentials(self) -> "Settings":
        import logging

        _logger = logging.getLogger("trading_bot.config")
        if self.TRADING_MODE == "live":
            if not self.POLYMARKET_PRIVATE_KEY:
                raise ValueError(
                    "TRADING_MODE=live requires POLYMARKET_PRIVATE_KEY to be set. "
                    "API credentials (api_key, api_secret, api_passphrase) are "
                    "auto-derived from the private key at startup."
                )
        if self.TRADING_MODE == "testnet":
            if not self.POLYMARKET_PRIVATE_KEY:
                raise ValueError(
                    "TRADING_MODE=testnet requires POLYMARKET_PRIVATE_KEY to be set."
                )
            if not self.POLYMARKET_BUILDER_API_KEY:
                _logger.warning(
                    "TRADING_MODE=testnet without POLYMARKET_BUILDER_API_KEY — "
                    "CLOB order placement will use standard auth (gas fees apply). "
                    "Set Builder credentials for gasless trading via Builder Program."
                )
        return self

    @property
    def SIMULATION_MODE(self) -> bool:
        """Backward-compat property — True for paper and testnet, False only for live."""
        return self.TRADING_MODE != "live"

    model_config = ConfigDict(env_file=".env")


settings = Settings()
