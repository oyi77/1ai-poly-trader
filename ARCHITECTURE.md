# PolyEdge Architecture

## Overview

PolyEdge is a full-stack automated prediction market trading bot targeting **Polymarket** and **Kalshi**. It combines AI-powered signal generation, multi-strategy execution, real-time market data aggregation, and a React dashboard for monitoring and control.

The system supports paper trading (shadow mode), live trading with risk controls, and comprehensive backtesting.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                    │
│  React 18 + TypeScript + Vite + TanStack Query + Tailwind            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │Dashboard │ │ Admin    │ │ Signals  │ │  Trades  │ │ GlobeView │  │
│  │Overview  │ │ Controls │ │  Table   │ │  Table   │ │  (3D Map) │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                               │ REST API (polling via TanStack Query)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         API LAYER (FastAPI)                           │
│  backend/api/main.py — Lifespan-managed, CORS, Prometheus metrics    │
│  81 routes: /api/v1/{signals,trades,strategies,risk,admin,...}       │
└──────────────────────────────────────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│  ORCHESTRATOR │    │  STRATEGY ENGINE  │    │  RISK MANAGER │
│  core/        │    │  strategies/      │    │  core/        │
│  orchestrator │    │  strategy_executor│    │  risk_manager │
│  .py          │    │  .py              │    │  .py          │
└──────┬───────┘    └────────┬─────────┘    └──────┬───────┘
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      STRATEGY MODULES                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────────┐ │
│  │BTC Momentum│ │Weather EMOS│ │Copy Trader │ │Market Maker        │ │
│  │btc_momentum│ │weather_emos│ │copy_trader │ │market_maker        │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────────┐ │
│  │BTC Oracle  │ │Kalshi Arb  │ │Bond Scanner│ │Whale PNL Tracker   │ │
│  │btc_oracle  │ │kalshi_arb  │ │bond_scanner│ │whale_pnl_tracker   │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────────────┘ │
│  ┌────────────────────────┐                                          │
│  │Realtime Scanner        │                                          │
│  │realtime_scanner        │                                          │
│  └────────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────────┘
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      AI / SIGNAL LAYER                                │
│  ai/ensemble.py — Multi-provider AI ensemble (Claude, Groq, Custom)  │
│  ai/sentiment_analyzer.py — Market sentiment via LLM                 │
│  ai/bayesian_optimizer.py — Parameter optimization                   │
│  core/signals.py, base_signals.py — Signal generation pipeline       │
└──────────────────────────────────────────────────────────────────────┘
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────────┐ │
│  │Polymarket  │ │Kalshi      │ │Crypto      │ │Weather             │ │
│  │CLOB Client │ │Client      │ │(Coinbase/  │ │(Open-Meteo GFS     │ │
│  │+ WebSocket │ │            │ │Kraken/     │ │ ensemble + NWS)    │ │
│  │(py-clob-   │ │(kalshi_    │ │Binance)    │ │                    │ │
│  │ client)    │ │ client.py) │ │(crypto.py) │ │(weather.py)        │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
       │                     │                      │
       ▼                     ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   STORAGE / QUEUE / MONITORING                        │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐ │
│  │ SQLite  │  │Redis Queue│  │APScheduler│  │Prometheus Metrics    │ │
│  │(primary)│  │(optional, │  │(cron jobs, │  │(monitoring/         │ │
│  │         │  │ falls back│  │ recurring  │  │ middleware.py)      │ │
│  │         │  │ to SQLite)│  │ scans)     │  │                    │ │
│  └─────────┘  └──────────┘  └───────────┘  └──────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     NOTIFICATIONS                                     │
│  bot/notification_router.py → Telegram, Discord (email de-scoped)    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
polyedge/
├── main.py                    # Entry point — starts FastAPI + background workers
├── run.py                     # Alternate runner with env validation
├── requirements.txt           # Python dependencies
├── docker-compose.yml         # Multi-service (app + Redis)
├── Dockerfile                 # Backend container
├── ecosystem.config.js        # PM2 process manager (API + worker + scheduler)
├── railway.json               # Railway.app deployment
├── vercel.json                # Vercel frontend deployment
├── pytest.ini                 # Test runner config
├── .env.example               # Required environment variables
│
├── backend/
│   ├── api/                   # FastAPI routes and middleware
│   │   └── main.py            # App factory, lifespan, CORS, routes
│   ├── core/                  # Orchestration, risk, scheduling, signals
│   │   ├── orchestrator.py    # Central coordination of strategies
│   │   ├── bankroll_reconciliation.py # BotState financial cache reconciliation
│   │   ├── risk_manager.py    # Position limits, circuit breakers
│   │   ├── strategy_executor.py # Strategy lifecycle management
│   │   ├── settlement.py      # Trade settlement tracking
│   │   ├── calibration.py     # Brier score, signal accuracy
│   │   ├── circuit_breaker.py # Automatic trading halts
│   │   └── scheduler.py       # APScheduler job definitions
│   ├── strategies/            # Trading strategy implementations
│   │   ├── base.py            # BaseStrategy + StrategyContext
│   │   ├── btc_momentum.py    # BTC 5-min microstructure
│   │   ├── weather_emos.py    # GFS ensemble weather
│   │   ├── copy_trader.py     # Whale copy trading
│   │   ├── market_maker.py    # Market making with inventory
│   │   ├── kalshi_arb.py      # Cross-platform arbitrage
│   │   ├── order_executor.py  # Order placement + management
│   │   └── registry.py        # Strategy registration
│   ├── ai/                    # AI signal providers
│   │   ├── ensemble.py        # Multi-provider ensemble
│   │   ├── claude.py          # Anthropic Claude provider
│   │   ├── groq.py            # Groq (Llama) provider
│   │   └── sentiment_analyzer.py
│   ├── data/                  # Market data clients
│   │   ├── polymarket_clob.py # Polymarket CLOB (py-clob-client)
│   │   ├── kalshi_client.py   # Kalshi REST API
│   │   ├── ws_client.py       # WebSocket market data
│   │   ├── crypto.py          # Coinbase/Kraken/Binance candles
│   │   └── weather.py         # Open-Meteo GFS ensemble
│   ├── bot/                   # Notifications (Telegram, Discord)
│   ├── models/                # SQLAlchemy models (Trade, Signal, etc.)
│   ├── cache/                 # Response caching layer
│   ├── monitoring/            # Prometheus metrics + middleware
│   ├── queue/                 # Job queue (Redis or SQLite fallback)
│   └── tests/                 # Backend test suite (pytest)
│
├── frontend/
│   ├── src/
│   │   ├── components/        # React components (Dashboard, Admin, GlobeView)
│   │   ├── hooks/             # TanStack Query hooks
│   │   ├── pages/             # Page-level components
│   │   └── test/              # Vitest unit tests
│   ├── e2e/                   # Playwright E2E tests
│   ├── vite.config.ts         # Vite build config
│   └── vitest.config.ts       # Test runner config
│
├── docs/                      # Project documentation
│   ├── how-it-works.md        # Strategy explanations
│   ├── api.md                 # API endpoint reference
│   ├── configuration.md       # Environment variables
│   ├── data-sources.md        # Data provider docs
│   ├── project-structure.md   # Codebase layout
│   └── architecture/          # ADRs (job queue, live equity source, etc.)
│
└── tests/                     # Root-level integration tests
```

---

## Core Data Flow

1. **Market Data Ingestion** — Data clients (`polymarket_clob.py`, `kalshi_client.py`, `crypto.py`, `weather.py`) fetch live market prices, orderbook depth, and external data (GFS ensemble forecasts, BTC candles)

2. **Strategy Execution** — The orchestrator triggers registered strategies on a schedule (APScheduler). Each strategy runs its signal generation logic using the latest market data.

3. **AI Signal Analysis** — For strategies that use AI, the ensemble layer queries multiple providers (Claude, Groq) and aggregates predictions with confidence scores.

4. **Risk Management** — Before any order, the risk manager validates position limits, portfolio concentration, circuit breaker status, and shadow mode flags.

5. **Order Execution** — `order_executor.py` places orders via the Polymarket CLOB SDK or Kalshi API. Supports limit orders, market orders, and partial fills.

6. **Settlement Tracking** — `settlement.py` + `settlement_helpers.py` monitor open positions and reconcile outcomes. In live mode, settlement preserves the trade ledger and delegates financial cache updates to `bankroll_reconciliation.py`.

7. **Dashboard Updates** — The React frontend polls the FastAPI backend via TanStack Query, rendering real-time signals, trades, strategy performance, and risk metrics.

---

## Financial State Source of Truth

`Trade` rows are the durable learning ledger and must not be deleted or reset to repair dashboard/risk cache drift. `BotState` is a derived cache.

- **Live mode**: `BotState.bankroll` and `BotState.total_pnl` are derived from external account equity: CLOB USDC cash balance plus Polymarket Data API open-position value. Local realized P&L/backfill rows are not authoritative for live equity.
- **Paper/testnet modes**: `BotState` remains ledger-derived from initial bankroll, realized P&L, and open exposure because these modes are simulated accounting environments.
- **Implementation**: `backend/core/bankroll_reconciliation.py` is the only intended writer for live financial cache fields. See `docs/architecture/adr-002-live-equity-source.md`.

---

## Trading Strategies

| Strategy | Module | Description |
|----------|--------|-------------|
| BTC Momentum | `btc_momentum.py` | RSI + momentum + VWAP on 1m/5m/15m candles |
| BTC Oracle | `btc_oracle.py` | AI-assisted BTC price predictions |
| Weather EMOS | `weather_emos.py` | GFS 31-member ensemble temperature forecasting |
| Copy Trader | `copy_trader.py` | Mirrors whale trader positions |
| Market Maker | `market_maker.py` | Spread quoting with inventory management |
| Kalshi Arbitrage | `kalshi_arb.py` | Cross-platform Polymarket↔Kalshi price gaps |
| Bond Scanner | `bond_scanner.py` | Fixed-income market opportunities |
| Whale PNL Tracker | `whale_pnl_tracker.py` | Tracks top trader realized PNL |
| Realtime Scanner | `realtime_scanner.py` | Price velocity signal detection |

---

## AGI Modules

The system includes an AGI-inspired intelligence layer for autonomous market analysis and strategy optimization:

- **Research Pipeline** — Automated gathering of market data, news sentiment, and social signals. Uses persistent storage for historical context.
- **Debate Engine** — Multi-agent consensus system where different LLM personas argue for and against specific trades to reduce bias.
- **Self-Review** — Post-trade analysis module that evaluates execution quality and signal accuracy.
- **Self-Improvement** — Feedback loop that adjusts strategy parameters and AI prompts based on historical performance.

---

## Infrastructure

- **Database**: SQLite (primary), PostgreSQL-ready via SQLAlchemy ORM
- **Job Queue**: Redis (preferred) with automatic SQLite fallback
- **Scheduler**: APScheduler for recurring market scans and settlement checks
- **Caching**: In-memory + optional Redis for API response caching
- **Monitoring**: Prometheus metrics endpoint (`/metrics`) with request/response middleware

---

## Deployment

- **Docker**: `docker-compose.yml` runs app + Redis containers
- **Railway**: Backend deploys via `railway.json` (auto-detected Python buildpack)
- **Vercel**: Frontend deploys via `vercel.json` (Vite static build)
- **PM2**: `ecosystem.config.js` manages API server, queue worker, and scheduler processes
- **CI**: GitHub Actions (`.github/`) runs tests on push

---

## Key Configuration

All configuration via environment variables (see `.env.example`):

- `TRADING_MODE` — `paper` (default) or `live`
- `SHADOW_MODE` — `true` to log signals without executing trades
- `AI_PROVIDER` — `groq`, `claude`, or `omniroute`
- `JOB_WORKER_ENABLED` — Enable background job processing
- `REDIS_URL` — Optional; falls back to SQLite queue if absent
- Feature flags for individual strategies and data sources
