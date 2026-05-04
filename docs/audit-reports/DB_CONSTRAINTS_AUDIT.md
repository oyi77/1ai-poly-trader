# Database Schema Constraints Audit

**Date**: 2026-05-04
**Scope**: All ORM models in `backend/models/` (6 files, 40+ tables)
**Files Analyzed**: `database.py`, `kg_models.py`, `outcome_tables.py`, `backtest.py`, `historical_data.py`, `hft_tables.py`

---

## Executive Summary

| Constraint Type | Count | Coverage |
|-----------------|-------|----------|
| ForeignKey constraints | 12 | Partial — 10 strategy references missing |
| Unique constraints | 13 | Good — entity_id, job idempotency, wallet_address, strategy_name, market_id, etc. |
| Check constraints | **0** | ❌ No enum validation for domain values |
| Indexes | 25+ | Good composite indexes, missing (strategy, timestamp) patterns |

---

## 🔴 Critical Gap — Missing Foreign Keys (10 tables)

Strategy name columns across the codebase reference `strategy_config.strategy_name` but lack ForeignKey constraints. This allows orphaned records if a strategy is deleted, and prevents cascade cleanup.

### Tables Missing Strategy FK (Priority Order)

**Core Trading (Immediate):**
1. `Trade.strategy` → should FK `strategy_config(strategy_name)` **SET NULL** (trades historical, keep but mark orphaned)
2. `TradeAttempt.strategy` → should FK `strategy_config(strategy_name)` **RESTRICT** (prevent delete if attempts exist)
3. `StrategyOutcome.strategy` → should FK `strategy_config(strategy_name)` **CASCADE** (delete outcomes with strategy)

**Learning/Audit (Important):**
4. `ParamChange.strategy` → CASCADE
5. `StrategyHealthRecord.strategy` → CASCADE
6. `TradingCalibrationRecord.strategy` → CASCADE
7. `MetaLearningRecord.strategy` → CASCADE
8. `BlockedSignalCounterfactual.strategy` → CASCADE
9. `EvolutionLineage.strategy_name` → CASCADE

**Signal/Tracking (Medium):**
10. `Signal.track_name` → unclear target; either create `edge_tracks` table or add CHECK constraint for known track names

---

## 🟡 Medium Gap — Missing CHECK Constraints (0 current)

No enum validation in schema. Invalid values can be inserted by bugs or migration scripts.

### Recommended CHECK Constraints

| Table | Column | Expected Values |
|-------|--------|-----------------|
| `trade` | `direction` | `'BUY'`, `'SELL'` |
| `trade` | `result` | `'win'`, `'loss'`, `'push'` |
| `signal` | `status` | `'pending'`, `'executed'`, `'rejected'` |
| `strategy_config` | `phase` | `'DRAFT'`, `'SHADOW'`, `'PAPER'`, `'LIVE_PROMOTED'`, `'RETIRED'` |
| `bot_state` | `mode` | `'paper'`, `'testnet'`, `'live'` |
| `transaction_event` | `transaction_type` | `'deposit'`, `'withdrawal'`, `'trade'`, `'settlement'` |
| `trade_attempt` | `status` | `'pending'`, `'succeeded'`, `'failed'`, `'canceled'` |
| `experiment` | `status` | `'DRAFT'`, `'SHADOW'`, `'PAPER'`, `'LIVE_PROMOTED'`, `'RETIRED'` |

---

## 🟢 Good Coverage

### Unique Constraints (13 defined)
- `entity_id` (KG entities)
- `experiment_name` (unique)
- `job_idempotency.key` (unique per job)
- `wallet_address` (unique)
- `strategy_name` (unique in `strategy_config`)
- `market_id` (unique in market tables)
- `alert_type` + `name` (unique in alerts)
- `settings.key` (unique)
- `fingerprint` (unique in backtest runs)
- `tx_hash` + `attempt_id` (unique in transaction events)

### Composite Indexes (25+)
- ✅ `job_queue(status, priority)` — job dequeue performance
- ✅ `hft_signals(market_id, created_at)` — HFT signal queries
- ✅ `performance_metrics(metric_type, timestamp)` — metric retrieval
- ✅ `error_logs(error_type, timestamp)` — error queries

---

## Missing Performance Indexes (Medium Priority)

No composite indexes on `(strategy, timestamp)` pattern, which is used extensively for strategy-scoped historical queries:

- `trades(strategy, created_at)` — strategy P&L history
- `signals(strategy_name, created_at)` — signal generation history
- `calibration_records(strategy, recorded_at)` — calibration tracking
- `strategy_health(strategy, recorded_at)` — health trend analysis
- `activity_log(strategy_name, timestamp)` — activity audit

Recommend: Add B-tree composite indexes on these column pairs.

---

## Recommended Alembic Migration Plan

### Phase 1 (Critical — immediate)
Add 3 strategy foreign keys:
1. `trade.strategy` → `strategy_config(strategy_name)` ON DELETE SET NULL
2. `trade_attempt.strategy` → `strategy_config(strategy_name)` ON DELETE RESTRICT
3. `strategy_outcome.strategy` → `strategy_config(strategy_name)` ON DELETE CASCADE

### Phase 2 (Important — this sprint)
Add remaining 6 strategy FKs (ParamChange, StrategyHealthRecord, TradingCalibrationRecord, MetaLearningRecord, BlockedSignalCounterfactual, EvolutionLineage) with ON DELETE CASCADE.

### Phase 3 (Hardening — next sprint)
Add 10+ CHECK constraints for enum columns (direction, result, status, phase, mode, transaction_type, etc.).
Add composite `(strategy, timestamp)` indexes on trades, signals, calibration_records, activity_log, strategy_health.

---

*Report generated: 2026-05-04 — 40+ tables analyzed across 6 model files*
