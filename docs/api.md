# API Reference

## API Versioning

All API endpoints are versioned using the `/v1` prefix. The current version is **v1**.

**Base URL**: `http://localhost:8000/api/v1`

**Version Detection**:
1. URL path: `/api/v1/...` (primary method)
2. Accept-Version header: `Accept-Version: v1` (fallback)

**Response Headers**:
- All responses include `X-API-Version: v1` header

**Invalid Version**:
- Returns 400 Bad Request if version is invalid or unsupported

**Documentation**: See `docs/api-versioning.md` for detailed versioning strategy.

## Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/dashboard` | GET | All dashboard data in one call |
| `/api/v1/btc/price` | GET | Current BTC price + momentum |
| `/api/v1/btc/windows` | GET | Active BTC 5-min windows |
| `/api/v1/signals` | GET | Current BTC trading signals |
| `/api/v1/signals/actionable` | GET | BTC signals above threshold |
| `/api/v1/kalshi/status` | GET | Kalshi API auth status + balance |
| `/api/v1/weather/forecasts` | GET | Ensemble forecasts for all cities |
| `/api/v1/weather/markets` | GET | Weather markets (Kalshi + Polymarket) |
| `/api/v1/weather/signals` | GET | Weather trading signals (both platforms) |
| `/api/v1/trades` | GET | Trade history |
| `/api/v1/stats` | GET | Bot statistics |
| `/api/v1/calibration` | GET | Signal calibration data |
| `/api/v1/run-scan` | POST | Trigger BTC + weather scan |
| `/api/v1/simulate-trade` | POST | Simulate a BTC trade |
| `/api/v1/settle-trades` | POST | Check settlements |
| `/api/v1/bot/start` | POST | Start trading |
| `/api/v1/bot/stop` | POST | Pause trading |
| `/api/v1/bot/reset` | POST | Reset all trades |
| `/api/v1/events` | GET | Event log |

## Health Check Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic health check (load balancers) |
| `/health/ready` | GET | Readiness check (dependencies) |
| `/health/detailed` | GET | Detailed system status |

See `docs/operations/monitoring.md` for health check details.

## System Monitoring Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/system/errors` | GET | Recent error logs |
| `/api/v1/system/aggregation` | GET | Error aggregation by type/endpoint |
| `/api/v1/system/rate` | GET | Current error rate (errors/minute) |
| `/api/v1/system/cleanup` | POST | Cleanup old error logs |
| `/api/v1/system/alerts` | GET | System alerts |
| `/api/v1/system/alerts/stats` | GET | Alert statistics |
| `/api/v1/system/alerts/{id}/resolve` | POST | Resolve alert |
| `/api/v1/system/metrics` | GET | Current system metrics |
| `/api/v1/system/audit-logs` | GET | Configuration change audit trail |
| `/metrics` | GET | Prometheus metrics |

See `docs/operations/monitoring.md` for monitoring details.

## WebSocket Endpoints

| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `/ws/markets` | WS | Market data updates (topic: "markets") |
| `/ws/whales` | WS | Whale trader activity (topic: "whales") |
| `/ws/events` | WS | Trading events (topic: "events") |
| `/ws/activities` | WS | Activity log (topic: "activities") |
| `/ws/brain` | WS | AI analysis (topic: "brain") |
| `/ws/dashboard-data` | WS | Dashboard stats (topic: "stats") |

**Subscription Protocol**:
```json
// Client sends after connection
{"action": "subscribe", "topic": "markets"}

// Server responds
{"type": "subscribed", "topic": "markets"}
```

## Rate Limiting

All endpoints are rate limited to prevent abuse:

**Rate Limit Tiers**:
- High-frequency: 100 requests/minute
- Medium-frequency: 50 requests/minute
- Low-frequency: 20 requests/minute

**Response Headers**:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

**429 Response**:
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "retry_after": 60
}
```

See `docs/operations/scalability.md` for rate limiting details.

## Authentication

Admin endpoints require authentication via `/api/v1/admin/login`. Set `ADMIN_PASSWORD` in environment or config.
