# PolyEdge — Prediction Market Trading Bot

A full-stack automated prediction market trading bot targeting **Polymarket** and **Kalshi**. Combines AI-powered signal generation, 9 trading strategies, real-time market data aggregation, and a React dashboard for monitoring and control.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![React](https://img.shields.io/badge/react-18+-61DAFB) ![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

![Dashboard](docs/dashboard.png)

## Overview

### Trading Strategies

| Strategy | Description |
|----------|-------------|
| **BTC Momentum** | RSI + momentum + VWAP on 1m/5m/15m candles from Coinbase/Kraken/Binance |
| **BTC Oracle** | AI-assisted BTC price predictions via ensemble LLM analysis |
| **Weather EMOS** | 31-member GFS ensemble temperature forecasting (Open-Meteo + NWS) |
| **Copy Trader** | Mirrors top whale trader positions from Polymarket leaderboard |
| **Market Maker** | Spread quoting with real-time inventory tracking |
| **Kalshi Arbitrage** | Cross-platform price gap detection (Polymarket ↔ Kalshi) |
| **Bond Scanner** | Fixed-income prediction market opportunities |
| **Whale PNL Tracker** | Tracks top trader realized PNL for signal generation |
| **Realtime Scanner** | Price velocity and momentum signal detection |

### Key Features

- **Multi-Strategy Engine** — 9 strategies running in parallel with per-strategy risk isolation
- **AI Ensemble** — Claude + Groq LLM providers for sentiment analysis and signal synthesis
- **Multi-Platform Trading** — Polymarket (CLOB SDK) and Kalshi (REST API) simultaneously
- **Edge Detection** — Identifies mispriced markets with configurable edge thresholds
- **Kelly Criterion Sizing** — Fractional Kelly position sizing with per-trade and portfolio caps
- **Signal Calibration** — Brier score tracking for prediction accuracy over time
- **Risk Management** — Circuit breakers, position limits, portfolio concentration guards
- **Shadow Mode** — Paper trading with virtual bankroll and equity curve tracking
- **Professional Dashboard** — React + TypeScript + TanStack Query with real-time updates
- **Job Queue** — Redis-backed (falls back to SQLite) for background strategy execution
- **Monitoring** — Prometheus metrics endpoint with request/response middleware

## Quick Start

### 1. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys (see docs/configuration.md)

# Run the backend
uvicorn backend.api.main:app --reload --port 8000
```

Backend will be at: http://localhost:8000
API docs at: http://localhost:8000/docs

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run the frontend
npm run dev
```

Frontend will be at: http://localhost:5173

### 3. Docker (Alternative)

```bash
docker-compose up -d
```

Starts the backend API + Redis. See `docker-compose.yml` for configuration.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                    │
│  React 18 + TypeScript + TanStack Query + Tailwind + Vite            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │Dashboard │ │ Admin    │ │ Signals  │ │  Trades  │ │ GlobeView │  │
│  │Overview  │ │ Controls │ │  Table   │ │  Table   │ │  (3D Map) │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                               │ REST API
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + Python)                         │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────────┐ │
│  │Orchestrator│ │  9 Trading│ │   Risk    │ │ AI Ensemble           │ │
│  │           │ │ Strategies│ │  Manager  │ │ (Claude + Groq)       │ │
│  └───────────┘ └───────────┘ └───────────┘ └───────────────────────┘ │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────────┐ │
│  │  Order    │ │Settlement │ │  Signal   │ │ Job Queue             │ │
│  │ Executor  │ │  Engine   │ │Calibration│ │ (Redis / SQLite)      │ │
│  └───────────┘ └───────────┘ └───────────┘ └───────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Polymarket│ │ Kalshi   │ │Coinbase/ │ │Open-Meteo│ │  NWS API   │ │
│  │CLOB SDK  │ │REST API  │ │Kraken/   │ │GFS       │ │            │ │
│  │+ WebSocket│ │         │ │Binance   │ │Ensemble  │ │            │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE: SQLite DB │ Redis Queue │ APScheduler │ Prometheus  │
│  DEPLOY: Docker Compose │ Railway (backend) │ Vercel (frontend)     │
│  NOTIFY: Telegram │ Discord                                          │
└──────────────────────────────────────────────────────────────────────┘
```

## Documentation

- **[How It Works](docs/how-it-works.md)** - Detailed explanation of BTC and weather strategies
- **[API Reference](docs/api.md)** - Complete API endpoint documentation
- **[Configuration](docs/configuration.md)** - All settings and environment variables
- **[Data Sources](docs/data-sources.md)** - Description of all data providers
- **[Project Structure](docs/project-structure.md)** - Codebase organization
- **[Job Queue Architecture](docs/architecture/adr-001-job-queue.md)** - Phase 1/2 queue design

## License

MIT - do whatever you want with it.
