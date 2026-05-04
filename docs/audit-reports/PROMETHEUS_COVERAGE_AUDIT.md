# Prometheus Metrics Coverage Inventory

**Date**: 2026-05-04
**Scope**: All Prometheus and custom metrics instrumentation in `backend/`
**Files Reviewed**: `monitoring/metrics.py`, `monitoring/hft_metrics.py`, `monitoring/performance_tracker.py`, `monitoring/queue_metrics.py`, `monitoring/middleware.py`, `core/*` and `strategies/*` for usage

---

## Currently Instrumented (26 metrics total)

### Prometheus Client Library (`monitoring/hft_metrics.py`) — 9 metrics

| Metric | Type | Labels | Status |
|--------|------|--------|--------|
| `hft_signals_total` | Counter | strategy, signal_type | ✅ Defined |
| `hft_execution_latency_seconds` | Histogram | strategy, status | ✅ Defined |
| `hft_market_scan_seconds` | Histogram | scanner | ✅ Defined |
| `hft_circuit_breaker_open_total` | Counter | name, reason | ✅ Defined |
| `hft_arb_opportunities_total` | Counter | type, profit_bucket | ✅ Defined |
| `hft_whale_activities_total` | Counter | action, size_bucket | ✅ Defined |
| `hft_execution_total` | Counter | strategy, side, status | ✅ Defined |
| `hft_position_pnl_dollars` | Gauge | strategy | ✅ Defined |
| `hft_open_positions` | Gauge | strategy | ✅ Defined |

⚠️ **Problem**: Defined but **never called** from `backend/core/hft_executor.py` — HFT execution path uninstrumented.

---

### Custom In-Memory Metrics (`monitoring/metrics.py`) — 17 metrics

| Metric | Type | Status |
|--------|------|--------|
| `trades_total` | Counter | ✅ Incremented in `strategy_executor.py` |
| `trades_winning` | Counter | ✅ Incremented on win |
| `trades_losing` | Counter | ✅ Incremented on loss |
| `signals_total` | Counter | ✅ Incremented in signal generators |
| `signals_executed` | Counter | ✅ Incremented on execution |
| `pnl_total_cents` | Gauge | ✅ Updated on settlement |
| `bankroll_cents` | Gauge | ✅ Updated on trade/settlement |
| `api_requests_total` | Counter | ✅ Incremented in middleware |
| `api_errors_total` | Counter | ✅ Incremented in middleware |
| `api_timeouts_total` | Counter | ✅ Incremented on timeout |
| `db_timeouts_total` | Counter | ✅ Incremented on DB timeout |
| `external_api_timeouts_total` | Counter | ✅ Incremented on external timeout |
| `scans_total` | Counter | ✅ Incremented in market scanner |
| `settlements_total` | Counter | ✅ Incremented in settlement |
| `avg_api_latency_ms` | Gauge | ✅ Moving average updated in middleware |
| `strategies_active` | Gauge | ✅ Updated on strategy enable/disable |
| `strategies_paused` | Gauge | ✅ Updated on pause/resume |

---

### Performance Tracking (`monitoring/performance_tracker.py`) — Defined but Not Called

| Method | Purpose | Call Status |
|--------|---------|-------------|
| `track_request(start, end, method, path, status)` | Request latency percentiles | ✅ Called from `middleware.py` |
| `track_db_query(start, end)` | DB query latency percentiles | ❌ **DEFINED BUT NEVER CALLED** |
| `track_websocket_latency(start, end)` | WebSocket latency percentiles | ❌ **DEFINED BUT NEVER CALLED** |

---

## 🔴 Critical Blind Spots (No Instrumentation)

### 1. Trade Execution Pipeline
**Files**: `core/auto_trader.py`, `core/risk_manager.py`, `strategies/order_executor.py`
- Signal acceptance/rejection counts (auto vs manual)
- Risk validation rejection reasons (drawdown, size limit, confidence threshold, exposure)
- Order placement attempts, rejections, fills, partial fills, cancellations
- Execution latency breakdown (risk check → order placement → fill)

**Impact**: Cannot diagnose why trades fail or measure execution quality.

---

### 2. Circuit Breaker State Transitions
**File**: `core/circuit_breaker.py`
- CLOSED→OPEN count (failure threshold breached)
- OPEN→HALF_OPEN (recovery timeout expiry)
- HALF_OPEN→CLOSED (probe success)
- HALF_OPEN→OPEN (probe failure)
- In-flight request count during OPEN state

**Impact**: Cannot diagnose cascading failures or recovery patterns.

---

### 3. Trade Settlement
**File**: `core/settlement.py`
- Settlement attempts per trade
- Settlement failures (outcome lookup error, DB update error)
- Settlement latency (trade → settled)
- Reconciliation gaps (settled locally but not on-chain)

**Impact**: Cannot detect settlement failures or reconciliation issues.

---

### 4. HFT Executor (Defined Metrics Never Called)
**File**: `core/hft_executor.py`
- `hft_execution_total` never incremented
- `hft_execution_latency_seconds` never recorded
- `hft_signals_total` never incremented
- `hft_position_pnl_dollars` never updated

**Impact**: HFT metrics collection completely non-functional.

---

### 5. Database Query Performance
**File**: `monitoring/performance_tracker.py`
- `track_db_query()` exists but **no calls** anywhere in codebase
- DB query latency percentiles (p50/p95/p99) always 0

**Impact**: Cannot identify slow queries or DB bottlenecks.

---

### 6. Error Type Distribution
**File**: `core/errors.py` (exception hierarchy defined)
- No counters per error type: `CircuitOpenError`, `DataQualityError`, `RiskViolation`, `SettlementError`, `MarketDataError`, `ExternalAPIError`

**Impact**: Cannot diagnose which error categories dominate failures.

---

### 7. Strategy Health & Performance
- Per-strategy win rate
- Per-strategy Sharpe ratio / max drawdown
- Per-strategy signal quality (Brier score)
- Per-strategy execution success rate
- Strategy auto-promotion readiness (fronttest validation metrics)

**Impact**: Cannot monitor individual strategy health or AGI promotion eligibility.

---

### 8. External API Reliability (Per-Endpoint)
- Per-API success rate (Polymarket CLOB, Kalshi, Gamma, Goldsky, Coinbase, Binance)
- Latency by endpoint (p50/p95/p99)
- Retry count per endpoint
- Fallback usage (when primary fails, secondary used)

**Impact**: Cannot diagnose which external APIs are problematic.

---

### 9. Data Feed Staleness
- Data freshness age (last update timestamp vs now)
- Feed lag (message timestamp vs receive time)
- Missed update count (heartbeat gaps)
- WebSocket reconnection count

**Impact**: Cannot detect data quality degradation or feed outages.

---

### 10. Bankroll Allocation Enforcement (AGI)
- Allocation violations (actual vs planned per-strategy capital)
- Rebalancing frequency
- Capital utilization by strategy (active vs idle)

**Impact**: Cannot verify AGI autonomy constraints are respected.

---

### 11. Job Queue Health (Redis/SQLite)
- Queue depth per job type (backlog size)
- Job timeout rate per type
- Job error rate per type
- Worker pool utilization

**Impact**: Cannot detect queue saturation or worker starvation.

---

### 12. Event Bus / SSE Delivery
- SSE client connection count
- Event publish rate vs delivery rate
- Event queue depth
- Dropped event count (slow subscribers)

**Impact**: Cannot monitor real-time dashboard health.

---

## Coverage Assessment Matrix

| System Event | Measured? | Metric Type | Gap Severity |
|--------------|-----------|-------------|--------------|
| Trades executed | ✅ Partial | Counter (total/win/loss) | Medium — no rejection reasons |
| Signals generated | ✅ Partial | Counter (total/executed) | Medium — no rejection breakdown |
| API latency | ✅ Yes | Percentiles (p50/p95/p99) | Low |
| API errors | ✅ Yes | Counter | Low |
| Circuit breaker trips | ✅ HFT only | Counter | **High** — core CB not instrumented |
| Order placements | ❌ No | — | **Critical** |
| Trade settlements | ❌ No | — | **Critical** |
| Risk rejections | ❌ No | — | **Critical** |
| DB query latency | ❌ No | Defined but unused | **High** |
| Error types | ❌ No | — | **High** |
| Strategy health | ❌ No | — | **High** |
| External API reliability | ❌ No | — | **High** |
| Data feed staleness | ❌ No | — | **Medium** |
| Bankroll allocation | ❌ No | — | **Medium** |
| Job queue health | ❌ No | — | **Medium** |
| SSE delivery health | ❌ No | — | **Low** |

---

## Key Structural Problems

1. **Two parallel metrics systems** (`hft_metrics.py` Prometheus + `metrics.py` custom in-memory) are disconnected and report to different backends.
2. **Middleware-only API tracking** — business logic execution path has zero instrumentation.
3. **Defined-but-uncalled methods** — `track_db_query()` and `track_websocket_latency()` exist but are never invoked.
4. **HFT metrics defined but never used** — `hft_executor.py` does not import or call any `hft_metrics` functions.

---

## Recommended Instrumentation Priority

**Phase 1 (Critical — this week):**
1. Instrument `auto_trader.py` — signal acceptance/rejection, risk decision outcomes
2. Instrument `risk_manager.py` — rejection reasons with labeled counters
3. Instrument `order_executor.py` — order placement/fill/cancel lifecycle
4. Fix `hft_executor.py` — connect all HFT metric calls
5. Activate `track_db_query()` in ORM layer (SQLAlchemy event listeners or query wrapper)

**Phase 2 (High — next sprint):**
6. Instrument `circuit_breaker.py` — state transition counters
7. Instrument `settlement.py` — settlement attempts/failures/latency
8. Add per-error-type counters in `error_logger.py`
9. Add per-API success/latency metrics in all external clients (polymarket_clob, kalshi_client, gamma, goldsky)

**Phase 3 (Medium — following sprint):**
10. Add per-strategy health metrics (win rate, Sharpe, drawdown)
11. Add data feed staleness metrics (last_update_age, reconnection_count)
12. Add bankroll allocation enforcement metrics
13. Consolidate custom in-memory metrics to Prometheus client for unified export

---

*Report generated: 2026-05-04 — 26 metrics found, 12 critical blind spots identified*
