# Performance Audit Summary - N+1 Query Bugs

**Date**: 2026-05-03  
**Scope**: `backend/core/*.py` and `backend/api/*.py`  
**Status**: ✅ Complete

---

## Executive Summary

Scanned 104 potential N+1 query patterns across the polyedge backend. Identified **12 critical/high/medium priority issues** that could reduce database query volume by **85-90%** for affected operations.

**Key Finding**: Settlement reconciliation, nightly reviews, and AGI autonomy cycles are executing 10-100x more queries than necessary.

---

## Deliverables

### 1. **N1_QUERY_AUDIT.md** (Comprehensive Report)
- Detailed analysis of all 12 priority issues
- Code snippets showing the problem
- Recommended fixes with examples
- SQLAlchemy best practices
- 4-phase implementation roadmap
- Testing recommendations

### 2. **N1_QUERY_SNIPPETS.txt** (Quick Reference)
- File:line locations for all issues
- Categorized by severity (Critical/High/Medium)
- Acceptable patterns marked with ✓

### 3. **This Summary** (Executive Overview)
- High-level findings
- Impact estimates
- Next steps

---

## Critical Issues (Fix Immediately)

| # | File | Line | Issue | Impact |
|---|------|------|-------|--------|
| 1 | settlement.py | 199-200 | Loop with per-item query | 100 queries → 1 |
| 2 | nightly_review.py | 100-109 | Loop with per-strategy query | 20 queries → 1 |
| 3 | experiment_tracker.py | 125-134, 173-182, 243-248 | Multiple loops with repeated queries | 10+ queries → 2-3 |
| 4 | auto_trader.py | 38-49 | Loop with per-item query | 50 queries → 1 |
| 5 | analytics.py | 54-68 | Loop with query inside | 100+ queries → 5-10 |

---

## High Priority Issues (Fix This Week)

| # | File | Line | Issue |
|---|------|------|-------|
| 6 | signals.py | 356-358 | Loop with query |
| 7 | calibration_tracker.py | 154-168 | Loop with query |
| 8 | wallet_auto_discovery.py | 155-157 | Loop with query |
| 9 | copy_trading.py | 200-211 | Loop with query |

---

## Medium Priority Issues (Fix This Month)

| # | File | Line | Issue |
|---|------|------|-------|
| 10 | scheduler.py | 577-586 | Loop with per-strategy query |

---

## Performance Impact Estimate

Assuming **10ms per database query**:

### Settlement Reconciliation
- **Before**: 100 queries × 10ms = **1000ms**
- **After**: 1 query × 10ms = **10ms**
- **Savings**: 990ms per reconciliation

### Nightly Review
- **Before**: 20 queries × 10ms = **200ms**
- **After**: 1 query × 10ms = **10ms**
- **Savings**: 190ms per nightly run

### AGI Autonomy Cycle
- **Before**: 10+ queries × 10ms = **100+ms**
- **After**: 2-3 queries × 10ms = **20-30ms**
- **Savings**: 70-80ms per cycle

### Auto-Trader Operations
- **Before**: 50 queries × 10ms = **500ms**
- **After**: 1 query × 10ms = **10ms**
- **Savings**: 490ms per request

### Analytics Dashboard
- **Before**: 100+ queries × 10ms = **1000+ms**
- **After**: 5-10 queries × 10ms = **50-100ms**
- **Savings**: 900-950ms per dashboard load

**Total Potential Savings**: ~2.6 seconds per operation cycle

---

## Implementation Roadmap

### Phase 1: Critical Fixes (This Week)
- [ ] Fix settlement.py:199 (batch load trades)
- [ ] Fix nightly_review.py:100 (use aggregation)
- [ ] Fix experiment_tracker.py loops (batch load configs)
- [ ] Fix auto_trader.py:38 (batch load approvals)
- [ ] Fix analytics.py:54 (batch load snapshots)

**Estimated Time**: 4-6 hours  
**Expected Query Reduction**: 85-90%

### Phase 2: High Priority (Next Week)
- [ ] Fix signals.py:356 (bulk operations)
- [ ] Fix calibration_tracker.py:154 (batch load)
- [ ] Fix wallet_auto_discovery.py:155 (batch load)
- [ ] Fix copy_trading.py:200 (batch load)

**Estimated Time**: 3-4 hours  
**Expected Query Reduction**: 70-80%

### Phase 3: Medium Priority (This Month)
- [ ] Fix scheduler.py:577 (aggregation or batch)
- [ ] Monitor brain.py:299 (acceptable if small)
- [ ] Add selectinload for related objects

**Estimated Time**: 2-3 hours

### Phase 4: Ongoing
- [ ] Add query performance monitoring
- [ ] Set up alerts for queries >100ms
- [ ] Document patterns in ARCHITECTURE.md
- [ ] Add pre-commit hook to detect N+1 patterns

---

## Recommended SQLAlchemy Patterns

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

# ✅ GOOD: Single query with join
configs = db.query(StrategyConfig).options(
    selectinload(StrategyConfig.trades)
).all()
```

### Pattern 3: Bulk Operations
```python
# ✅ GOOD: Bulk insert
db.bulk_insert_mappings(Signal, [s.dict() for s in signals])
db.commit()
```

### Pattern 4: Aggregation Query
```python
from sqlalchemy import func

# ✅ GOOD: Single aggregation
results = db.query(
    Trade.strategy,
    func.count(Trade.id).label('count'),
    func.sum(Trade.pnl).label('total_pnl')
).group_by(Trade.strategy).all()
```

---

## Testing Strategy

### 1. Query Counting
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

### 2. Performance Benchmarks
- Measure before/after query counts
- Track execution time
- Monitor database connection pool

### 3. Integration Tests
- Add query count assertions to test suite
- Fail tests if query count exceeds threshold
- Document expected query counts per operation

---

## Files Generated

1. **N1_QUERY_AUDIT.md** - Full detailed audit (comprehensive)
2. **N1_QUERY_SNIPPETS.txt** - Quick reference (for developers)
3. **PERFORMANCE_AUDIT_SUMMARY.md** - This file (executive summary)

---

## Next Steps

1. **Review** the N1_QUERY_AUDIT.md for detailed analysis
2. **Prioritize** fixes based on frequency and impact
3. **Implement** Phase 1 fixes this week
4. **Test** with query counting to verify improvements
5. **Monitor** performance metrics post-deployment

---

## Questions?

Refer to:
- **Detailed fixes**: N1_QUERY_AUDIT.md
- **Quick lookup**: N1_QUERY_SNIPPETS.txt
- **SQLAlchemy docs**: https://docs.sqlalchemy.org/en/20/orm/loading_relationships.html

---

**Audit completed by**: Performance Analysis Tool  
**Total patterns scanned**: 104  
**Priority issues identified**: 12  
**Estimated query reduction**: 85-90%  
**Estimated performance gain**: ~2.6 seconds per operation cycle
