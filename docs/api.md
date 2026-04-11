# API Reference

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | All dashboard data in one call |
| `/api/btc/price` | GET | Current BTC price + momentum |
| `/api/btc/windows` | GET | Active BTC 5-min windows |
| `/api/signals` | GET | Current BTC trading signals |
| `/api/signals/actionable` | GET | BTC signals above threshold |
| `/api/kalshi/status` | GET | Kalshi API auth status + balance |
| `/api/weather/forecasts` | GET | Ensemble forecasts for all cities |
| `/api/weather/markets` | GET | Weather markets (Kalshi + Polymarket) |
| `/api/weather/signals` | GET | Weather trading signals (both platforms) |
| `/api/trades` | GET | Trade history |
| `/api/stats` | GET | Bot statistics |
| `/api/calibration` | GET | Signal calibration data |
| `/api/run-scan` | POST | Trigger BTC + weather scan |
| `/api/simulate-trade` | POST | Simulate a BTC trade |
| `/api/settle-trades` | POST | Check settlements |
| `/api/bot/start` | POST | Start trading |
| `/api/bot/stop` | POST | Pause trading |
| `/api/bot/reset` | POST | Reset all trades |
| `/api/events` | GET | Event log |
| `/ws/events` | WS | Real-time event stream |

## Authentication

Admin endpoints require authentication via `/api/admin/login`. Set `ADMIN_PASSWORD` in environment or config.
