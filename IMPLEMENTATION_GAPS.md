# PolyEdge — Implementation Status & Known Gaps

**Last Updated**: 2026-04-30

## Summary

This document tracks what is implemented, what was intentionally de-scoped, and what remains incomplete. It is the honest source of truth — no false "100% Complete" claims.

---

## Backend

### Fully Implemented
- 9 trading strategies registered and executing (BTC Momentum, Weather EMOS, Copy Trader, Market Maker, Kalshi Arb, Bond Scanner, BTC Oracle, Whale PNL Tracker, Realtime Scanner)
- Polymarket CLOB integration via `py-clob-client` and `py-order-utils`
- Kalshi REST API client (`backend/data/kalshi_client.py`)
- AI ensemble layer with Claude, Groq, and custom providers
- Risk manager with position limits and circuit breakers
- Settlement tracking and P&L reconciliation
- Shadow mode (paper trading) with virtual bankroll
- Job queue with Redis primary and SQLite fallback
- APScheduler for recurring strategy scans
- Prometheus metrics endpoint and monitoring middleware
- WebSocket market data client (`ws_client.py`)
- **AGI Intelligence Layer**: Research Pipeline, Debate Engine, Self-Review, and Self-Improvement modules
- **AGI Level 5 TRUE-AGI Layer**: RegimeDetector, KnowledgeGraph, StrategyComposer, DynamicPromptEngine, AGIGoalEngine, SelfDebugger, StrategySynthesizer, ExperimentRunner, CausalReasoner, AGIOrchestrator, LLMCostTracker, AGIPromotionPipeline, RegimeAwareAllocator — all with full TDD test coverage (304 tests across 22 test files)
- **AGI Frontend**: AGIControlPanel, DecisionAuditLog, StrategyComposerUI, RegimeDisplay, AGIControl page, AGI API module

### Intentionally De-Scoped
- **Email notifications**: `notification_router.py` routes to Telegram and Discord only. Email channel raises `NotImplementedError` — this is a deliberate design choice, not a bug. Telegram and Discord cover all notification needs.

### Fixed (April 2026 Audit)
- Pydantic v2 `ConfigDict` migration (was using deprecated `class Config`)
- SQLAlchemy 2.0 `declarative_base` import (was using deprecated `ext.declarative`)
- FastAPI lifespan context manager (was using deprecated `@app.on_event`)
- `inspect.iscoroutinefunction` (was using deprecated `asyncio.iscoroutinefunction`)
- Market maker inventory tracking now queries real database (was returning placeholder `0`)
- WebSocket `subscribe()` method is now properly `async` with `await`
- Backend deprecation warnings reduced from ~69,000 to 17

### Known Gaps — Backend
- **Exception handling**: ~306 `except Exception` blocks across 77 files. Critical-path modules (orchestrator, order_executor, risk_manager, strategy_executor, api/main, polymarket_clob, settlement_helpers) and non-critical modules (core, strategies, data, AI) now have structured error logging. Remaining blocks in peripheral modules are low priority.
- ~~**Database migrations**: No Alembic setup.~~ → **Fixed**: Alembic initialized with autogenerate from current schema. Initial migration at `alembic/versions/51c2bc15c671_initial_schema.py`.
- **Kalshi API**: Base URL `https://api.elections.kalshi.com/trade-api/v2` confirmed working (returns 200). Authenticated endpoints (portfolio, orders) require valid `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH`. The 404 was from testing without credentials.
- **Polymarket Testnet Clarification**: The Polymarket Builder Program operates on MAINNET (chain_id=137), not a separate testnet. The "testnet" mode in PolyEdge uses mainnet CLOB with Builder auth for gasless trading. There is no functional testnet CLOB host (clob-staging.polymarket.com returns 503). Testnet trades are REAL but gasless; track separately from paper/live modes.
- **AGI LLM Cost Tracking**: LLMCostTracker uses in-memory storage only. Costs reset on process restart. For production, persist daily spend to database.
- **AGI Strategy Synthesizer**: Generates Python strategy code via LLM but does not yet auto-validate against live market data. Strategies must pass manual review before shadow deployment.
- **AGI Knowledge Graph**: SQLite-backed with rollback capability. For high-frequency production use, consider migrating to a graph database (Neo4j) for better query performance on large entity graphs.

---

## Frontend

### Fully Implemented
- React 18 + TypeScript + Vite dashboard
- TanStack Query for server state management
- Dashboard overview, signals table, trades table, admin controls
- GlobeView 3D map component (Three.js / react-three-fiber)
- Playwright E2E test suite
- Vitest unit test suite (9 files, 36 tests — all passing)
- **AGI Control Panel**: Emergency stop, status display, goal override (AGIControlPanel.tsx)
- **Decision Audit Log**: Paginated decision log with regime/goal filters (DecisionAuditLog.tsx)
- **Strategy Composer UI**: Drag-to-compose strategy blocks interface (StrategyComposerUI.tsx)
- **Regime Display**: Regime icons, confidence gauge, goal status card, history timeline (RegimeDisplay.tsx)
- **AGI Control Page**: Tabbed AGI page with NavLink routing (AGIControl.tsx)
- **AGI API Module**: Typed API client for AGI endpoints (api/agi.ts)

### Fixed (April 2026 Audit)
- Vitest config now includes correct `src/**/*.test.{ts,tsx}` pattern (was picking up Playwright e2e files)
- OpportunityScanner test mocks `../api` module instead of global `fetch`
- WhaleActivityFeed test mocks `../api` module instead of global `fetch`
- PendingApprovals test wraps component with `QueryClientProvider`

### Known Gaps — Frontend
    - **Bundle size**: GlobeView lazy-loaded in OverviewTab + manualChunks splits three-globe (1MB), three (569KB), recharts (408KB) into separate chunks. Main index.js is 57KB. All page routes lazy-loaded. Further reduction requires replacing three-globe dependency.
- **Offline/error states**: Some components lack loading skeletons and error boundaries.

---

## Infrastructure

### Implemented
- Docker Compose (app + Redis)
- Railway deployment config (`railway.json`)
- Vercel frontend deployment (`vercel.json`)
- PM2 process manager (API + worker + scheduler)
- GitHub Actions CI pipeline
- `.env.example` with all required variables documented

### Known Gaps — Infrastructure
- **Grafana dashboards**: Prometheus metrics are collected but no dashboards are configured. Future work.
- **Log aggregation**: Structured logging exists but no centralized log collection (e.g., Loki, CloudWatch).

---

## Documentation

### Current State
- `ARCHITECTURE.md` — Accurate system architecture, directory structure, data flow, strategies, AGI Intelligence Layer (updated April 2026)
- `README.md` — Project overview, quick start, architecture diagram, doc links
- `docs/how-it-works.md` — Strategy explanations
- `docs/api.md` — API endpoint reference
- `docs/configuration.md` — Environment variables
- `docs/data-sources.md` — Data provider documentation
- `docs/project-structure.md` — Codebase layout (updated April 2026)
- `docs/architecture/adr-001-job-queue.md` — Job queue design decision
- `docs/architecture/adr-005-static-risk-profiles-and-learning-boundary.md` — Risk boundary ADR
- `docs/architecture/adr-006-agi-autonomy-framework.md` — AGI autonomy boundaries ADR

### Known Gaps — Documentation
- No runbook for production operations (deployment, rollback, incident response)

---

## Future Work (Not In Current Scope)

1. ~~**Alembic migrations** — Proper schema versioning for production database changes~~ → **Done** (April 2026)
2. **Grafana dashboards** — Visual monitoring for Prometheus metrics
3. ~~**Full exception audit** — Cover remaining bare `except Exception` blocks~~ → Critical + non-critical modules now have structured logging (April 2026)
4. ~~**Frontend code splitting** — Lazy-load heavy page components~~ → All pages lazy-loaded + manualChunks configured (April 2026). GlobeView lazy-loaded in OverviewTab. Remaining three-globe (1MB) is external library weight.
5. **Kalshi live trading validation** — Verify API endpoints with active credentials
6. **Load testing** — Stress test concurrent strategy execution and API throughput
7. ~~**Per-trade RL learning** — Weekly batch job replaced with event-driven `realtime_learner.on_trade_settled()`~~ → **Done** (April 2026)
8. ~~**Paper bankroll top-up** — `POST /api/v1/bot/paper-topup` + frontend control room button~~ → **Done** (April 2026)
9. ~~**Admin settings API** — `GET/POST /api/admin/settings` with grouped+masked output, `GET /api/admin/system`~~ → **Done** (April 2026)
10. ~~**Rate limiter test bypass** — `"unknown"` client ID (no-IP test clients) now bypassed alongside `"testclient"`~~ → **Done** (April 2026)
