# Global Mutable State Race Conditions Audit

**Date**: 2026-05-04
**Scope**: `backend/core/*.py` — module-level mutable state written from async contexts without lock protection
**Total Globals Analyzed**: 13

---

## Executive Summary

| Risk Level | Count | Description |
|------------|-------|-------------|
| 🔴 CRITICAL (no lock, concurrent writes) | 5 | `event_log`, scheduler singletons, `_last_param_change`, `_cal_cache`, `_recent_alerts` |
| ✅ Protected (with lock) | 5 | `_settings_cache`, `_pending_heartbeats`, `_settlement_lock`, `_trade_execution_lock`, `_write_lock` |
| 🔵 LOW (double-init benign) | 3 | `_error_logger`, `_applier_instance`, `_settlement_handler` |

---

## 🔴 CRITICAL RACE CONDITIONS (Immediate Fix Required)

### 1. `scheduler.py` — `event_log: List[dict] = []` (line 65)

- **Lock Status**: ❌ No lock
- **Write Paths**:
  - Line 77: `event_log.append(event)` in `log_event()` (called from async APScheduler jobs)
  - Line 80: `event_log.pop(0)` in `log_event()` (same function)
- **Risk**: Concurrent append/pop from multiple async job invocations can corrupt list structure or drop events. List mutation is not atomic in CPython under GIL release points (I/O, await).
- **Impact**: Lost monitoring/debugging events; possible list corruption crashing scheduler.
- **Fix**: Wrap mutations with `threading.Lock()` or `asyncio.Lock()`; consider `collections.deque` with lock for thread-safe atomic operations.

---

### 2. `scheduler.py` — `scheduler`, `queue`, `worker`, `worker_task` globals (lines 57–61)

- **Lock Status**: ❌ No lock
- **Write Paths**:
  - `start_scheduler()` (line 193, 645–646) initializes all four
  - `stop_scheduler()` (line 716–717) sets `worker = None`, `worker_task = None`
- **Read Paths**: Multiple — orchestrator, jobs, worker task
- **Risk**: Concurrent start/stop calls (or read during write) cause double-initialization or use-after-free. No synchronization barrier.
- **Impact**: Scheduler lifecycle corruption; worker task lost reference; crash on restart.
- **Fix**: Add `asyncio.Lock` guarding entire start/stop sequence; use double-checked locking pattern or encapsulate in SchedulerManager class.

---

### 3. `auto_improve.py` — `_last_param_change: Optional[dict] = None` (line 42)

- **Lock Status**: ❌ No lock
- **Write Paths**:
  - Line 185, 193: `_last_param_change = None` in `check_rollback_needed()` (sync)
  - Line 291: `_last_param_change = {...}` in `auto_improve_job()` (async, weekly)
- **Read Paths**:
  - Line 110: `if _last_param_change is None:` in `check_rollback_needed()`
  - Lines 114–148: Multiple dict key reads during rollback check
- **Risk**: TOCTOU race — `check_rollback_needed()` may read dict while `auto_improve_job()` mid-write, seeing partially-initialized dict or key errors.
- **Impact**: Incorrect rollback decision; parameter state corruption.
- **Fix**: Protect all reads/writes with `threading.Lock()`; or move state to DB with atomic transaction.

---

### 4. `calibration.py` — `_cal_cache: Dict[str, dict] = {}` (line 25)

- **Lock Status**: ❌ No lock
- **Write Paths**:
  - `_load()` (line 32, 35): `_cal_cache = json.loads(...)` or `_cal_cache = {}` (sync)
  - `update_calibration()` (line 80): `_cal_cache.update(cal)` — called from `settlement_helpers.py:809` (async settlement job)
- **Read Paths**:
  - `_load()` (line 30): `if not _cal_cache and ...`
  - `get_sigma()` (line 44): `cal = _load()` — called from weather signal generation
- **Risk**: Concurrent `_load()` and `update()` can cause dict corruption or lost calibration updates. CPython dict mutation is not thread-safe for concurrent writes.
- **Impact**: Incorrect weather forecast calibration → degraded signal quality.
- **Fix**: Add `threading.Lock` around all `_cal_cache` accesses; or use `collections.defaultdict` with lock.

---

### 5. `heartbeat.py` — `_recent_alerts: dict[str, datetime] = {}` (line 16)

- **Lock Status**: ❌ No lock (NOT protected by `_hb_lock`, which guards `_pending_heartbeats` only)
- **Write Paths**:
  - Line 162: `_recent_alerts[h["name"]] = now_dt` in `watchdog_job()` (async, runs every minute)
- **Read Paths**:
  - Line 160: `last_alert = _recent_alerts.get(h["name"])` in same `watchdog_job()` (same async function)
- **Risk**: Concurrent reads/writes within same async task are safe due to GIL, but if `watchdog_job()` re-enters (multiple watchdog checks overlapping due to slow I/O), dict mutation not atomic.
- **Impact**: Alert deduplication may miss or duplicate notifications.
- **Fix**: Use `_hb_lock` (already present) to also guard `_recent_alerts`; or add separate `threading.Lock`.

---

## ✅ PROTECTED GLOBAL STATE (Safe Patterns)

| File | Variable | Lock Type | Status |
|------|----------|-----------|--------|
| `config_service.py:12` | `_settings_cache` | `threading.Lock` (`_cache_lock`) | SAFE |
| `heartbeat.py:19` | `_pending_heartbeats` | `threading.Lock` (`_hb_lock`) | SAFE |
| `settlement.py:26` | `_settlement_lock` | `asyncio.Lock` | SAFE |
| `strategy_executor.py:33` | `_trade_execution_lock` | `asyncio.Lock` | SAFE |
| `activity_logger.py:20` | `_write_lock` | `threading.Lock` | SAFE |

---

## 🔵 LOW-RISK SINGLETONS (Double-Init Only)

These use lazy initialization without lock. Two concurrent first-calls may create duplicate instances, but instances are stateless or internally locked — benign race.

| File | Variable | Risk | Notes |
|------|----------|------|-------|
| `error_logger.py:231` | `_error_logger` | LOW | `ErrorLogger` has internal `asyncio.Lock`; duplicate harmless |
| `proposal_applier.py:261` | `_applier_instance` | LOW | Stateless class; duplicate harmless |
| `settlement_ws.py:177` | `_settlement_handler` | MEDIUM | Concurrent init + shutdown may cause use-after-free; add `asyncio.Lock` |

---

## Summary Table

| File | Variable | Type | Lock Protected? | Severity |
|------|----------|------|-----------------|----------|
| `scheduler.py` | `event_log` | list | ❌ NO | 🔴 HIGH |
| `scheduler.py` | `scheduler, queue, worker, worker_task` | singletons | ❌ NO | 🔴 HIGH |
| `auto_improve.py` | `_last_param_change` | dict | ❌ NO | 🔴 HIGH |
| `calibration.py` | `_cal_cache` | dict | ❌ NO | 🔴 HIGH |
| `heartbeat.py` | `_recent_alerts` | dict | ❌ NO | 🔴 HIGH |
| `settlement_ws.py` | `_settlement_handler` | singleton | ❌ NO | 🟠 MEDIUM |
| `error_logger.py` | `_error_logger` | singleton | ❌ NO (but safe) | 🔵 LOW |
| `proposal_applier.py` | `_applier_instance` | singleton | ❌ NO (but safe) | 🔵 LOW |
| `config_service.py` | `_settings_cache` | dict | ✅ YES | SAFE |
| `heartbeat.py` | `_pending_heartbeats` | dict | ✅ YES | SAFE |
| `settlement.py` | `_settlement_lock` | asyncio.Lock | ✅ YES | SAFE |
| `strategy_executor.py` | `_trade_execution_lock` | asyncio.Lock | ✅ YES | SAFE |
| `activity_logger.py` | `_write_lock` | threading.Lock | ✅ YES | SAFE |

---

## Remediation Priority

1. **Immediate (P0)**: Protect `event_log` and scheduler globals in `scheduler.py` — affects core orchestration
2. **High (P1)**: Add lock to `_last_param_change` in `auto_improve.py` — AGI parameter rollback integrity
3. **High (P1)**: Add lock to `_cal_cache` in `calibration.py` — weather forecast accuracy
4. **High (P1)**: Add lock to `_recent_alerts` in `heartbeat.py` — use existing `_hb_lock`
5. **Medium (P2)**: Add `asyncio.Lock` to `_settlement_handler` lifecycle in `settlement_ws.py`

---

*Report generated: 2026-05-04 — 13 module-level mutable state items audited across 12 core files*
