# Configuration

All settings in `backend/config.py`, overridable via environment variables.

## BTC Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `SCAN_INTERVAL_SECONDS` | 60 | BTC scan frequency |
| `MIN_EDGE_THRESHOLD` | 0.02 | Minimum edge (2%) |
| `MAX_ENTRY_PRICE` | 0.55 | Max entry price (55c) |
| `MAX_TRADE_SIZE` | 75.0 | Max $ per BTC trade |
| `KELLY_FRACTION` | 0.15 | Fractional Kelly multiplier |

## Kalshi Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `KALSHI_API_KEY_ID` | None | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PATH` | None | Path to RSA private key PEM file |
| `KALSHI_ENABLED` | True | Enable/disable Kalshi market fetching |

## Weather Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `WEATHER_ENABLED` | True | Enable/disable weather trading |
| `WEATHER_SCAN_INTERVAL_SECONDS` | 300 | Weather scan frequency (5 min) |
| `WEATHER_MIN_EDGE_THRESHOLD` | 0.08 | Minimum edge (8%) |
| `WEATHER_MAX_ENTRY_PRICE` | 0.70 | Max entry price (70c) |
| `WEATHER_MAX_TRADE_SIZE` | 100.0 | Max $ per weather trade |
| `WEATHER_CITIES` | nyc,chicago,miami,los_angeles,denver | Cities to track |

## Risk Management

| Setting | Default | Description |
|---------|---------|-------------|
| `DAILY_LOSS_LIMIT` | 300.0 | Daily loss circuit breaker |
| `MAX_TOTAL_PENDING_TRADES` | 20 | Max open positions |
| `INITIAL_BANKROLL` | 10000.0 | Starting paper bankroll |

## Job Queue

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_WORKER_ENABLED` | `False` | Opt-in worker process |
| `JOB_QUEUE_URL` | `sqlite:///./job_queue.db` | Queue backend |
| `JOB_TIMEOUT_SECONDS` | `300` | Per-job timeout |
| `MAX_CONCURRENT_JOBS` | `1` | Worker concurrency limit |
| `CACHE_URL` | `sqlite:///./cache.db` | Cache backend |

## Unified State Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_INTERVAL_TESTNET` | `60` | Testnet sync interval (seconds) |
| `SYNC_INTERVAL_LIVE` | `30` | Live mode sync interval (seconds) |
| `SYNC_SETTLEMENT_INTERVAL` | `120` | Settlement verification interval (seconds) |

The bot automatically syncs with the Polymarket blockchain in live and testnet modes to:
- Import external trades made outside the bot
- Verify settlement status of open positions
- Detect orphaned positions (on blockchain but not in database)
- Update trade metadata with blockchain verification timestamps

## Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./polyedge.db` | Database connection URL |
| `DATABASE_POOL_SIZE` | `20` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | Max overflow connections |
| `DATABASE_POOL_TIMEOUT` | `30` | Pool timeout (seconds) |
| `DATABASE_POOL_RECYCLE` | `3600` | Connection recycle time (seconds) |
| `DATABASE_QUERY_TIMEOUT` | `10.0` | Query timeout (seconds) |

## Redis Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `REDIS_ENABLED` | `True` | Enable Redis pub/sub |

Redis is used for:
- Multi-instance WebSocket broadcasting
- Pub/sub messaging across backend instances
- Falls back to in-process broadcasting if unavailable

## Timeout Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_REQUEST_TIMEOUT` | `30.0` | API request timeout (seconds) |
| `DATABASE_QUERY_TIMEOUT` | `10.0` | Database query timeout (seconds) |
| `EXTERNAL_API_TIMEOUT` | `15.0` | External API timeout (seconds) |

## Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `True` | Enable rate limiting |
| `RATE_LIMIT_HIGH_FREQ` | `100` | High-frequency endpoints (requests/minute) |
| `RATE_LIMIT_MEDIUM_FREQ` | `50` | Medium-frequency endpoints (requests/minute) |
| `RATE_LIMIT_LOW_FREQ` | `20` | Low-frequency endpoints (requests/minute) |

## Connection Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_WEBSOCKET_PER_IP` | `10` | Max WebSocket connections per IP |
| `MAX_HTTP_PER_IP` | `50` | Max HTTP connections per IP |
| `MAX_HTTP_GLOBAL` | `1000` | Max global HTTP connections |

## Circuit Breaker Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_ENABLED` | `True` | Enable circuit breakers |
| `DB_CIRCUIT_FAIL_MAX` | `5` | Database failure threshold |
| `DB_CIRCUIT_TIMEOUT` | `60` | Database reset timeout (seconds) |
| `API_CIRCUIT_FAIL_MAX` | `3` | API failure threshold |
| `API_CIRCUIT_TIMEOUT` | `30` | API reset timeout (seconds) |

## Monitoring Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_ENABLED` | `True` | Enable Prometheus metrics |
| `METRICS_PORT` | `8000` | Metrics endpoint port |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ERROR_LOG_RETENTION_DAYS` | `30` | Error log retention period |

## Alert Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTS_ENABLED` | `True` | Enable alert system |
| `ALERT_COOLDOWN_MINUTES` | `5` | Alert cooldown period |
| `ERROR_RATE_THRESHOLD` | `10` | Error rate threshold (errors/minute) |
| `MEMORY_USAGE_THRESHOLD` | `80` | Memory usage threshold (%) |
| `DISK_SPACE_THRESHOLD` | `10` | Disk space threshold (% free) |

## Backup Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | `True` | Enable automated backups |
| `BACKUP_INTERVAL_HOURS` | `1` | Backup frequency (hours) |
| `BACKUP_RETENTION_DAYS` | `7` | Backup retention period |
| `BACKUP_VERIFICATION_ENABLED` | `True` | Enable backup verification |

## MiroFish Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `MIROFISH_API_URL` | `https://api.mirofish.example/v1` | MiroFish API endpoint |
| `MIROFISH_API_KEY` | None | MiroFish authentication key |
| `MIROFISH_API_TIMEOUT` | `10` | API request timeout (seconds) |

MiroFish provides dual debate system integration:
- When enabled: Routes debate requests to MiroFish API for AI-powered signal analysis
- When disabled or on failure: Falls back to local debate engine automatically
- Credentials stored in database with priority: Database → Environment → Defaults
- Test connection via Settings UI before enabling

## Admin Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_PASSWORD` | None | Admin panel password (required) |
| `ADMIN_SESSION_TIMEOUT` | `3600` | Session timeout (seconds) |
