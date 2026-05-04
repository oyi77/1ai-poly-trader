# Database Session Management Audit

**Date**: 2026-05-04
**Scope**: All `SessionLocal()` instantiations in `backend/`
**Total Occurrences**: 189 across 30+ files

---

## Executive Summary

| Management Pattern | Count | Percentage | Safety |
|-------------------|-------|------------|--------|
| ✅ WITH_STATEMENT (`with SessionLocal() as db:`) | 34 | 18.0% | Safe |
| ✅ TRY_FINALLY (`db.close()`) | 26 | 13.7% | Safe |
| ✅ CONDITIONAL (`db = db or SessionLocal()`) | 20 | 10.6% | Safe |
| ❌ UNCHECKED (`db = SessionLocal()` no close) | 108 | 57.2% | **Unsafe** |
| ❌ RETURN_UNCHECKED (returned without close) | 1 | 0.5% | **Critical** |

**57.7% of database sessions are leaked** — connection pool exhaustion risk under load.

---

## 🔴 Critical: Returned Without Close

### `backend/ai/self_review.py:156`

```python
def get_review(db: Session = None) -> dict:
    db = db or SessionLocal()
    # ... do work ...
    return db  # ❌ Returns open session to caller with no close guarantee
```

**Risk**: Caller receives open session and may never close it → connection leak.
**Fix**: Refactor to return data, not session; or require caller to manage session lifecycle explicitly.

---

## 🟠 High-Risk Files (≥4 unchecked calls)

| File | Unchecked | Safe | Total | Notes |
|------|-----------|------|-------|-------|
| `backend/ai/proposal_generator.py` | 5 | 1 | 6 | Lines 105, 396, 430, 471, 519 unchecked |
| `backend/api/lifespan.py` | 4 | 0 | 4 | Startup/shutdown handlers — leaks early |
| `backend/bot/telegram_bot.py` | 5 | 2 | 7 | Long-running bot process — cumulative leak |
| `backend/core/backtester.py` | 3 | 1 | 4 | Backtest runs can be long — high session count |
| `backend/job_queue/sqlite_queue.py` | 4 | 2 | 6 | Worker pool — repeated job execution leaks |

---

## Safe Patterns (Use as Templates)

### Pattern A: WITH_STATEMENT (Preferred)
```python
with SessionLocal() as db:
    rows = db.query(Model).filter(...).all()
# db auto-closed
```

### Pattern B: TRY_FINALLY
```python
db = SessionLocal()
try:
    rows = db.query(Model).all()
finally:
    db.close()
```

### Pattern C: CONDITIONAL (accept injected session)
```python
def process(db: Session = None):
    db = db or SessionLocal()
    try:
        # work
        result = ...
        if db is locals().get('_external_db'):  # caller provided
            return result, db
        return result
    finally:
        if db is not locals().get('_external_db'):
            db.close()
```

---

## 🟡 Unchecked Patterns by File (108 calls)

### `backend/ai/` (highest concentration)
- `claude.py`: 3 unchecked (lines 102, 171, 243)
- `impact_measurer.py`: 1 unchecked (line 303)
- `logger.py`: 1 unchecked (line 112)
- `mirofish_client.py`: 1 unchecked (line 78)
- `proposal_generator.py`: 5 unchecked (lines 105, 396, 430, 471, 519)
- `self_review.py`: 1 unchecked + 1 return (lines 156 is return unchecked)

### `backend/api/`
- `auto_trader.py`: 2 unchecked (lines 18, 82) + 2 safe try/finally (lines 111, 137)
- `lifespan.py`: 4 unchecked (lines 118, 232, 430, 655) — startup/shutdown critical path

### `backend/bot/`
- `telegram_bot.py`: 5 unchecked (multiple handlers)

### `backend/core/`
- `backtester.py`: 3 unchecked (lines 75, 437, 611) + 1 safe with-statement (line 233)
- `cache_cleanup.py`: 1 unchecked (line 81)
- `llm_cost_tracker.py`: 1 unchecked (line 64)

### `backend/job_queue/`
- `sqlite_queue.py`: 4 unchecked (lines 103, 206, 240, 275) + 2 safe (lines 150, and one with-statement)

---

## Recommended Migration Plan

### Phase 1 (High Priority — this week)
Fix session leaks in long-running processes:
1. `telegram_bot.py` handlers — all DB accesses
2. `lifespan.py` startup/shutdown — critical initialization
3. `sqlite_queue.py` worker job execution — repeated execution leaks
4. `self_review.py:156` — return path

### Phase 2 (Medium Priority — next sprint)
Convert remaining 100+ unchecked calls across:
- All `backend/ai/*` modules (proposal generator, claude, impact_measurer, etc.)
- All `backend/core/*` modules (backtester, cache_cleanup, llm_cost_tracker)
- All `backend/api/*` modules (auto_trader and others)

### Automation Opportunity
Write a codemod (using `bowler` or `libCST`) to automatically convert:
```python
db = SessionLocal()
# ... body ...
```
into:
```python
with SessionLocal() as db:
    # ... body ...
```
for cases without try/finally already. Requires AST analysis to avoid false positives (cases where db is returned/passed out).

---

## Linter Rule Recommendation

Add custom flake8/pylint rule to flag bare `SessionLocal()` assignment without subsequent `db.close()` within same function scope.

Example rule logic:
- Detect `db = SessionLocal()` (or `session = SessionLocal()`)
- Check function body for `db.close()` or `with` context wrapping the assignment
- Raise error if neither present

---

*Report generated: 2026-05-04 — 189 SessionLocal() instantiations audited; 108 (57.7%) require conversion to safe patterns*
