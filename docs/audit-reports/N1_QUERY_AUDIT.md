# N+1 Query Performance Audit - Polyedge

**Generated**: 2026-05-03  
**Scope**: `backend/core/*.py` and `backend/api/*.py`  
**Total Issues Found**: 104 potential N+1 patterns

---

## CRITICAL ISSUES (Immediate Fix Required)

### 1. `backend/core/settlement.py:199-200`
**Severity**: 🔴 CRITICAL  
**Frequency**: Runs during settlement reconciliation (potentially 100+ trades)

```python
for trade_id in trades_to_close:
    trade = db.query(Trade).filter(Trade.id == trade_id).first()  # ❌ N+1
```

**Problem**: If `trades_to_close` has 100 items, executes 100 separate queries  
**Fix**:
```python
trades_map = {t.id: t for t in db.query(Trade).filter(Trade.id.in_(trades_to_close)).all()}
for trade_id in trades_to_close:
    trade = trades_map.get(trade_id)
```

---

### 2. `backend/core/nightly_review.py:100-109`
**Severity**: 🔴 CRITICAL  
**Frequency**: Runs nightly for all strategies (typically 15-30 strategies)

```python
configs = db.query(StrategyConfig).all()
for cfg in configs:
    trades = db.query(Trade).filter(
        Trade.strategy == cfg.strategy_name,
        Trade.timestamp >= week_ago,
        Trade.settled.is_(True),
    ).all()  # ❌ N+1 (one query per strategy)
```

**Problem**: If 20 strategies, executes 20 queries instead of 1  
**Fix**:
```python
# Option 1: Single query with group_by
from sqlalchemy import func
trades_by_strategy = db.query(
    Trade.strategy,
    func.count(Trade.id).label('count'),
    func.sum(Trade.pnl).label('total_pnl')
).filter(
    Trade.timestamp >= week_ago,
    Trade.settled.is_(True)
).group_by(Trade.strategy).all()

# Option 2: Load all trades once, filter in memory
all_trades = db.query(Trade).filter(
    Trade.timestamp >= week_ago,
    Trade.settled.is_(True)
).all()
trades_by_strategy = {}
for trade in all_trades:
    if trade.strategy not in trades_by_strategy:
        trades_by_strategy[trade.strategy] = []
    trades_by_strategy[trade.strategy].append(trade)
```

---

### 3. `backend/core/experiment_tracker.py:125-134, 173-182, 243-248`
**Severity**: 🔴 CRITICAL  
**Frequency**: Runs during AGI autonomy promotion cycles (multiple times per day)

```python
# Line 125-134
for a in active:
    db.query(StrategyConfig).filter(...)  # ❌ N+1

# Line 173-182
for c in current:
    db.query(StrategyConfig).filter(...)  # ❌ N+1

# Line 243-248
for c in candidates:
    db.query(Experiment).filter(...)  # ❌ N+1
```

**Problem**: Repeated queries for same data in loops  
**Fix**: Load all configs/experiments once before loop:
```python
all_configs = db.query(StrategyConfig).all()
config_map = {c.strategy_name: c for c in all_configs}

for a in active:
    config = config_map.get(a.strategy_name)
```

---

### 4. `backend/api/auto_trader.py:38-49`
**Severity**: 🔴 CRITICAL  
**Frequency**: Called on every pending trade approval request

```python
for r in rows:
    row = db.query(PendingApproval).filter(PendingApproval.id == trade_id).first()  # ❌ N+1
```

**Problem**: If 50 pending trades, executes 50 queries  
**Fix**:
```python
pending_ids = [r.id for r in rows]
pending_map = {p.id: p for p in db.query(PendingApproval).filter(PendingApproval.id.in_(pending_ids)).all()}
for r in rows:
    row = pending_map.get(r.id)
```

---

### 5. `backend/api/analytics.py:54-68`
**Severity**: 🔴 CRITICAL  
**Frequency**: Called on every analytics dashboard request

```python
for r in ranked:
    db.query(EquitySnapshot)...  # ❌ N+1
```

**Problem**: Per-item database hits for equity snapshots  
**Fix**: Batch load all snapshots before loop:
```python
all_snapshots = db.query(EquitySnapshot).all()
snapshot_map = {s.id: s for s in all_snapshots}
for r in ranked:
    snapshot = snapshot_map.get(r.id)
```

---

## HIGH PRIORITY ISSUES (Fix This Week)

### 6. `backend/core/signals.py:356-358`
**Severity**: 🟠 HIGH  
**Frequency**: Runs on every signal generation cycle

```python
for signal in to_save:
    db.query(Signal).filter(...)  # ❌ N+1
```

**Fix**: Use bulk operations:
```python
db.bulk_insert_mappings(Signal, [s.dict() for s in to_save])
db.commit()
```

---

### 7. `backend/core/calibration_tracker.py:154-168`
**Severity**: 🟠 HIGH  
**Frequency**: Runs during calibration updates

```python
for r in records:
    query = db.query(CalibrationRecord).filter(...)  # ❌ N+1
```

**Fix**: Batch load before loop:
```python
record_ids = [r.id for r in records]
all_records = db.query(CalibrationRecord).filter(CalibrationRecord.id.in_(record_ids)).all()
record_map = {r.id: r for r in all_records}
```

---

### 8. `backend/core/wallet_auto_discovery.py:155-157`
**Severity**: 🟠 HIGH  
**Frequency**: Runs during wallet discovery

```python
for wallet in suggested:
    db.query(WalletConfig)...  # ❌ N+1
```

**Fix**: Batch load wallet configs:
```python
all_wallets = db.query(WalletConfig).all()
wallet_map = {w.address: w for w in all_wallets}
```

---

### 9. `backend/api/copy_trading.py:200-211`
**Severity**: 🟠 HIGH  
**Frequency**: Runs on copy trading operations

```python
for e in entries:
    db.query(...)  # ❌ N+1
```

**Fix**: Batch load entries before loop

---

## MEDIUM PRIORITY ISSUES (Fix This Month)

### 10. `backend/core/scheduler.py:577-586`
**Severity**: 🟡 MEDIUM  
**Frequency**: Runs hourly

```python
for config in db.query(StrategyConfig).filter(StrategyConfig.enabled == True).all():
    trades = db.query(Trade).filter(
        Trade.strategy == config.strategy_name,
        ...
    ).all()  # ❌ N+1
```

**Fix**: Use single query with aggregation or batch load

---

### 11. `backend/api/dashboard.py:150`
**Severity**: ✅ ACCEPTABLE  
**Status**: Uses `.in_()` for batch loading - GOOD PATTERN

```python
for context in db.query(TradeContext).filter(TradeContext.trade_id.in_(trade_ids)).all()
```

This is the correct pattern - no fix needed.

---

### 12. `backend/api/brain.py:299`
**Severity**: 🟡 MEDIUM  
**Frequency**: Called on every brain status request

```python
for config in db.query(StrategyConfig).all():
    strategies.append({...})
```

**Status**: Acceptable if StrategyConfig table is small (<100 rows). Monitor if grows.

---

## SUMMARY TABLE

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| settlement.py | 199 | Loop with per-item query | 🔴 CRITICAL | 100+ queries per reconciliation |
| nightly_review.py | 100 | Loop with per-strategy query | 🔴 CRITICAL | 20+ queries per nightly run |
| experiment_tracker.py | 125, 173, 243 | Multiple loops with queries | 🔴 CRITICAL | 10+ queries per AGI cycle |
| auto_trader.py | 38 | Loop with per-item query | 🔴 CRITICAL | 50+ queries per request |
| analytics.py | 54 | Loop with query | 🔴 CRITICAL | 100+ queries per dashboard load |
| signals.py | 356 | Loop with query | 🟠 HIGH | 50+ queries per signal cycle |
| calibration_tracker.py | 154 | Loop with query | 🟠 HIGH | 20+ queries per calibration |
| wallet_auto_discovery.py | 155 | Loop with query | 🟠 HIGH | 10+ queries per discovery |
| copy_trading.py | 200 | Loop with query | 🟠 HIGH | 30+ queries per operation |
| scheduler.py | 577 | Loop with per-strategy query | 🟡 MEDIUM | 20+ queries per hour |

---

## RECOMMENDED SQLALCHEMY PATTERNS

### Pattern 1: Batch Load with `.in_()`
```python
# ❌ BAD: N+1
for id in ids:
    obj = db.query(Model).filter(Model.id == id).first()

# ✅ GOOD: Single query
objs = db.query(Model).filter(Model.id.in_(ids)).all()
obj_map = {obj.id: obj for obj in objs}
```

### Pattern 2: Eager Loading with `selectinload`
```python
from sqlalchemy.orm import selectinload

# ❌ BAD: N+1
configs = db.query(StrategyConfig).all()
for cfg in configs:
    trades = cfg.trades  # Triggers query per config

# ✅ GOOD: Single query with join
configs = db.query(StrategyConfig).options(
    selectinload(StrategyConfig.trades)
).all()
```

### Pattern 3: Bulk Operations
```python
# ❌ BAD: N+1
for signal in signals:
    db.add(signal)
    db.commit()

# ✅ GOOD: Bulk insert
db.bulk_insert_mappings(Signal, [s.dict() for s in signals])
db.commit()
```

### Pattern 4: Aggregation Query
```python
from sqlalchemy import func

# ❌ BAD: N+1
for strategy in strategies:
    count = db.query(func.count(Trade.id)).filter(
        Trade.strategy == strategy
    ).scalar()

# ✅ GOOD: Single aggregation
results = db.query(
    Trade.strategy,
    func.count(Trade.id).label('count')
).group_by(Trade.strategy).all()
```

---

## IMPLEMENTATION ROADMAP

### Phase 1: Critical Fixes (This Week)
- [ ] Fix settlement.py:199 (batch load trades)
- [ ] Fix nightly_review.py:100 (use aggregation or batch load)
- [ ] Fix experiment_tracker.py loops (batch load configs)
- [ ] Fix auto_trader.py:38 (batch load pending approvals)
- [ ] Fix analytics.py:54 (batch load snapshots)

### Phase 2: High Priority (Next Week)
- [ ] Fix signals.py:356 (bulk operations)
- [ ] Fix calibration_tracker.py:154 (batch load)
- [ ] Fix wallet_auto_discovery.py:155 (batch load)
- [ ] Fix copy_trading.py:200 (batch load)

### Phase 3: Medium Priority (This Month)
- [ ] Fix scheduler.py:577 (aggregation or batch)
- [ ] Monitor brain.py:299 (acceptable if small table)
- [ ] Add selectinload for related objects where applicable

### Phase 4: Ongoing
- [ ] Add query performance monitoring
- [ ] Set up alerts for queries taking >100ms
- [ ] Document query patterns in ARCHITECTURE.md
- [ ] Add pre-commit hook to detect N+1 patterns

---

## TESTING RECOMMENDATIONS

1. **Query Counting**: Use SQLAlchemy event listeners to count queries
```python
from sqlalchemy import event

query_count = 0
@event.listens_for(Engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
    global query_count
    query_count += 1

# Run operation
operation()
print(f"Executed {query_count} queries")
```

2. **Performance Benchmarks**: Add before/after metrics
3. **Integration Tests**: Verify query counts in test suite

---

## REFERENCES

- SQLAlchemy Eager Loading: https://docs.sqlalchemy.org/en/20/orm/loading_relationships.html
- N+1 Query Problem: https://en.wikipedia.org/wiki/N%2B1_problem
- Bulk Operations: https://docs.sqlalchemy.org/en/20/orm/persistence_techniques.html#bulk-insert-mappings
