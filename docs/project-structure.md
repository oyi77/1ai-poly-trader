# Project Structure

```
kalshi-trading-bot/
├── backend/
│   ├── api/
│   │   ├── main.py                 # FastAPI routes + dashboard
│   │   ├── auth.py                 # Admin authentication
│   │   ├── markets.py              # Market data endpoints
│   │   ├── trading.py              # Trading endpoints
│   │   ├── phase2.py               # Production Phase 2 endpoints
│   │   ├── system.py               # Admin/bot management
│   │   └── ws_manager.py           # WebSocket management
│   ├── core/
│   │   ├── signals.py              # BTC signal generation
│   │   ├── weather_signals.py      # Weather signal generation
│   │   ├── scheduler.py            # Background jobs (BTC + weather)
│   │   ├── scheduling_strategies.py # Job strategy classes
│   │   ├── settlement.py           # Trade settlement (routes by market_type)
│   │   ├── settlement_helpers.py   # Settlement helper functions
│   │   ├── event_bus.py            # Event publishing system
│   │   └── errors.py               # Exception hierarchy
│   ├── data/
│   │   ├── btc_markets.py          # Polymarket BTC market fetcher
│   │   ├── crypto.py               # BTC price + microstructure
│   │   ├── kalshi_client.py        # Kalshi API client (RSA-PSS auth)
│   │   ├── kalshi_markets.py       # Kalshi weather market fetcher (KXHIGH)
│   │   ├── weather.py              # Open-Meteo ensemble + NWS observations
│   │   ├── weather_markets.py      # Polymarket weather market fetcher
│   │   └── markets.py              # Generic market wrapper
│   ├── models/
│   │   └── database.py             # SQLAlchemy models (market_type column)
│   ├── strategies/
│   │   ├── copy_trader.py          # Copy trading main logic
│   │   ├── wallet_sync.py          # Wallet sync helper
│   │   └── order_executor.py       # Order execution helper
│   └── config.py                   # All settings (BTC + weather)
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── dashboard/
│   │   │   │   ├── OverviewTab.tsx   # Main 3-column overview
│   │   │   │   ├── TradesTab.tsx    # Trade history table
│   │   │   │   ├── SignalsTab.tsx   # Signal history table
│   │   │   │   ├── MarketsTab.tsx   # Market data tabs
│   │   │   │   ├── LeaderboardTab.tsx # Copy trader leaderboard
│   │   │   │   ├── DecisionsTab.tsx # Strategy decision logs
│   │   │   │   └── PerformanceTab.tsx # Metrics and charts
│   │   │   ├── admin/
│   │   │   │   ├── StrategiesTab.tsx # Strategy controls
│   │   │   │   ├── MarketWatchTab.tsx # Market watch CRUD
│   │   │   │   ├── WalletConfigTab.tsx # Wallet management
│   │   │   │   ├── CredentialsTab.tsx # Trading mode config
│   │   │   │   ├── TelegramTab.tsx # Telegram notifications
│   │   │   │   ├── RiskTab.tsx # Risk parameters
│   │   │   │   └── AITab.tsx # AI provider config
│   │   │   ├── GlobeView.tsx        # 3D globe with city markers
│   │   │   ├── EdgeDistribution.tsx # Edge distribution chart
│   │   │   ├── MicrostructurePanel.tsx # RSI gauge + indicator meters
│   │   │   ├── WeatherPanel.tsx     # Weather forecasts per city
│   │   │   ├── CalibrationPanel.tsx # Prediction accuracy tracking
│   │   │   ├── StatsCards.tsx       # Performance metrics
│   │   │   ├── SignalsTable.tsx     # BTC + Weather signals combined
│   │   │   ├── TradesTable.tsx      # Trade history
│   │   │   ├── EquityChart.tsx      # P&L chart
│   │   │   └── Terminal.tsx         # Event log + controls
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        # Main dashboard
│   │   │   └── Admin.tsx            # Admin panel
│   │   ├── api.ts                   # API client
│   │   └── types.ts                 # TypeScript interfaces
│   └── package.json
├── requirements.txt
├── run.py
└── README.md
```
