# Prediction Market Trading Bot

A multi-strategy trading bot that identifies pricing inefficiencies in prediction markets. Combines **BTC 5-minute microstructure analysis** with **ensemble weather forecasting** to trade on **Kalshi** and **Polymarket**. Features a professional React dashboard.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![React](https://img.shields.io/badge/react-18+-61DAFB) ![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

![Dashboard](docs/dashboard.png)

**100% free to run** - No paid APIs, no subscriptions. All data sources are free. Kalshi API key optional for Kalshi markets.

## Overview

### Strategy 1: BTC 5-Minute Up/Down
Scans Polymarket BTC 5-minute Up/Down markets every 60 seconds. Uses real-time 1-minute candle data from Coinbase/Kraken/Binance to compute RSI, momentum, VWAP deviation, SMA crossover, and market skew as a weighted composite signal. Trades when edge > 2%.

### Strategy 2: Weather Temperature (Kalshi + Polymarket)
Scans weather temperature markets on **Kalshi** (KXHIGH series) and **Polymarket** every 5 minutes. Uses 31-member GFS ensemble forecasts from Open-Meteo to estimate the probability of temperature thresholds being exceeded. Trades when edge > 8%. Kalshi markets are auto-discovered via the `KXHIGHNY`, `KXHIGHCHI`, `KXHIGHMIA`, `KXHIGHLAX`, `KXHIGHDEN` series tickers.

### Key Features

- **BTC Microstructure Analysis** - RSI, momentum (1m/5m/15m), VWAP, SMA crossover from real candle data
- **Ensemble Weather Forecasting** - 31-member GFS ensemble from Open-Meteo for probabilistic temperature predictions
- **Multi-Platform Trading** - Trades weather markets on both Kalshi (KXHIGH series) and Polymarket simultaneously
- **Edge Detection** - Identifies mispriced markets across both strategies and platforms
- **Kelly Criterion Sizing** - Fractional Kelly (15%) position sizing with per-trade caps
- **Signal Calibration** - Tracks predictions vs outcomes with Brier score
- **Professional Dashboard** - React 3-column dashboard with real-time updates
- **Simulation Mode** - Paper trading with virtual bankroll tracking and equity curves

## Quick Start

### 1. Backend Setup

```bash
cd kalshi-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

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

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          FRONTEND                                │
│  React + TypeScript + TanStack Query + Tailwind                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │Indicators│ │ Weather  │ │ Signals  │ │  Trades  │            │
│  │  + Chart │ │  Panel   │ │  Table   │ │  Table   │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                          BACKEND                                 │
│  FastAPI + Python + SQLite + APScheduler                         │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐        │
│  │  BTC      │ │ Weather   │ │  Signal   │ │Settlement │        │
│  │ Signals   │ │ Signals   │ │ Scheduler │ │  Engine   │        │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Coinbase/ │ │Open-Meteo│ │  NWS     │ │Polymarket│ │ Kalshi │ │
│  │Kraken/   │ │ Ensemble │ │  API     │ │Gamma API │ │  API   │ │
│  │Binance   │ │  (GFS)   │ │          │ │          │ │(KXHIGH)│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
└──────────────────────────────────────────────────────────────────┘
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
