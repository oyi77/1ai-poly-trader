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
