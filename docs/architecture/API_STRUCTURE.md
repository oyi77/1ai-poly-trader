# API Structure Documentation

## Overview

The backend API has been modularized into separate router modules following SOLID principles. Each module is responsible for a specific domain of functionality.

## API Modules

### `backend/api/main.py` (766 lines, down from 3188)

Main FastAPI application that aggregates all sub-routers. This is the entry point for the application and handles:

- Importing and registering all sub-routers (auth, markets, trading, phase2, system, ws_manager)
- CORS configuration
- Application initialization
- No longer contains inline route implementations

### `backend/api/auth.py`

All authentication and admin management endpoints:

- `/api/admin/login` - Admin authentication
- `/api/admin/verify` - Token verification
- `/api/admin/logout` - Session termination

### `backend/api/markets.py`

Market data endpoints for all platforms:

- `/polymarket/*` - Polymarket market data
- `/btc/*` - BTC price and windows
- `/kalshi/*` - Kalshi market data
- `/weather/*` - Weather forecast data

### `backend/api/trading.py`

Trading-related endpoints:

- `/trades/*` - Trade history and management
- `/signals/*` - Signal history and actionable signals
- `/settlements/*` - Settlement status and execution

### `backend/api/phase2.py`

Active production Phase 2 endpoints:

- `/api/whales` - Whale tracking
- `/api/arbitrage` - Arbitrage opportunities
- `/api/news` - News sentiment
- `/api/predictions` - AI predictions

### `backend/api/system.py`

Admin and bot management endpoints:

- `/admin/*` - Admin configuration
- `/bot/*` - Bot control (start, stop, reset, scan)

### `backend/api/ws_manager.py`

WebSocket connection management:

- Event-based subscription system
- Market data streaming (`/ws/markets`, `/ws/whales`)
- Event log streaming (`/ws/events`)
- Client connection lifecycle management

## Core Infrastructure

### `backend/core/event_bus.py`

Event publishing system:

- `EventBus` class with `subscribe()`, `publish()`, `get_history()` methods
- Module-level instance (no singleton pattern)
- Replaces module-level `_event_subscribers` and `_event_history` from main.py

### Error Handling

`backend/core/errors.py` defines the exception hierarchy:

- `PolyEdgeException` (base)
- `MarketDataError`
- `TradingError`
- `ConfigurationError`

The `@handle_errors` decorator provides consistent logging across all API routes.

## Import Pattern

```python
# In main.py, import and register sub-routers
from backend.api import auth, markets, trading, phase2, system, ws_manager

app.include_router(auth.router, prefix="/api/admin")
app.include_router(markets.router)
app.include_router(trading.router, prefix="/api")
app.include_router(phase2.router, prefix="/api")
app.include_router(system.router)
app.include_router(ws_manager.router, prefix="/ws")
```

## Circular Import Resolution

The circular dependency between `polygon_listener.py` and `main.py` was resolved by:

- Moving `broadcast_whale_tick` to `ws_manager.py`
- `polygon_listener.py` now imports from `ws_manager` directly
- No imports from `backend.api.main` exist in production code
