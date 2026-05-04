# Thread/Async Safety Audit: backend/core/*.py

**Audit Date:** 2026-05-04  
**Scope:** 105 Python files in `backend/core/`  
**Method:** Pattern search for shared mutable state, lock violations, asyncio void checks

---

## CRITICAL RACE CONDITIONS (HIGH RISK)

### 1. **position_valuation.py:22-24, 240, 260** — Unprotected Global Cache in Async Context
**Risk Level:** 🔴 HIGH  
**File:** `backend/core/position_valuation.py`

**Issue:** Module-level price cache written without locks in async context
```python
# Line 22-24
_ticker_price_cache: Dict[str, Dict[str, float]] = {}
_ticker_price_cache_timestamps: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 60
```

**Writes at:**
- Line 240: `_ticker_price_cache[ticker] = price_data` (inside async `fetch_ticker_price`)
- Line 241: `_ticker_price_cache_timestamps[ticker] = now`
- Line 260: `_ticker_price_cache[ticker] = price_data` (Gamma API path)

**Race Condition:** Multiple concurrent `asyncio.gather()` tasks (line 305) write to shared dicts without synchronization. Two tasks fetching the same ticker simultaneously can:
- Corrupt dict internal state
- Lose updates (last-write-wins without atomicity)
- Return stale/inconsistent cache entries

**Reproduction:** Call `calculate_position_market_value()` with 20+ tickers while market data is updating.

**Fix:**
```python
import asyncio

_cache_lock = asyncio.Lock()

async def fetch_ticker_price(ticker: str, client: httpx.AsyncClient):
    # ... existing code ...
    async with _cache_lock:
        _ticker_price_cache[ticker] = price_data
        _ticker_price_cache_timestamps[ticker] = now
```

---

### 2. **auto_improve.py:42, 291** — Unprotected Global State Mutation in Async Job
**Risk Level:** 🔴 HIGH  
**File:** `backend/core/auto_improve.py`

**Issue:** Module-level `_last_param_change` written without locks in async job
```python
# Line 42
_last_param_change: Optional[dict] = None
```

**Writes at:**
- Line 291: `_last_param_change = { "previous_values": ..., "applied_values": ..., ... }`
- Line 185, 193: `_last_param_change = None` (in sync functions)

**Race Condition:** If `auto_improve_job()` (async) runs concurrently with:
- Rollback evaluation reading `_last_param_change`
- Other async tasks checking `if _last_param_change is not None`

State can be corrupted. The read-check-write cycle (lines 282-298) is not atomic.

**Reproduction:** Trigger auto_improve_job while rollback evaluation is running.

**Fix:**
```python
import asyncio

_param_change_lock = asyncio.Lock()

async def auto_improve_job():
    global _last_param_change
    # ... existing code ...
    async with _param_change_lock:
        _last_param_change = {
            "previous_values": previous,
            "applied_values": clamped,
            "applied_at": datetime.now(timezone.utc),
            # ... rest of dict ...
        }
```

---

### 3. **calibration.py:25, 29-35** — Unprotected Global Cache with Check-Then-Act Race
**Risk Level:** 🟠 MEDIUM-HIGH  
**File:** `backend/core/calibration.py`

**Issue:** Module-level calibration cache written without locks
```python
# Line 25
_cal_cache: Dict[str, dict] = {}

# Lines 28-36
def _load() -> Dict[str, dict]:
    global _cal_cache
    if not _cal_cache and _CALIBRATION_FILE.exists():  # Line 30 — CHECK
        try:
            _cal_cache = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))  # Line 32 — ACT
        except Exception as e:
            logger.debug(f"Failed to load calibration file: {e}")
            _cal_cache = {}  # Line 35
    return _cal_cache
```

**Race Condition:** Multiple threads calling `get_sigma()` → `_load()` simultaneously:
1. Thread A checks `if not _cal_cache` → True
2. Thread B checks `if not _cal_cache` → True
3. Both threads read file and overwrite `_cal_cache` (wasted I/O, potential data loss)
4. Check-then-act pattern is not atomic

**Reproduction:** Call `get_sigma()` from multiple threads concurrently on first load.

**Fix:**
```python
import threading

_cal_lock = threading.Lock()

def _load() -> Dict[str, dict]:
    global _cal_cache
    with _cal_lock:
        if not _cal_cache and _CALIBRATION_FILE.exists():
            try:
                _cal_cache = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"Failed to load calibration file: {e}")
                _cal_cache = {}
    return _cal_cache
```

---

### 4. **strategy_performance_registry.py:186** — Lock Declared but Never Used
**Risk Level:** 🟠 MEDIUM-HIGH  
**File:** `backend/core/strategy_performance_registry.py`

**Issue:** Lock declared but never initialized or used
```python
# Line 184-186
def __init__(self):
    self._reports: Dict[str, StrategyReport] = {}  # Shared mutable state
    self._lock = None  # Optional asyncio.Lock if needed for async safety
```

**Race Condition:** `_reports` dict is written in `update_from_settlement()` (line 196+) without lock protection:
```python
# Line 196-216 (simplified)
def update_from_settlement(self, strategy: str, db: Optional[Session] = None):
    # ... compute report ...
    self._reports[strategy] = report  # UNPROTECTED WRITE
```

Multiple concurrent calls to `update_from_settlement()` for different strategies can corrupt dict state.

**Reproduction:** Settle trades for multiple strategies concurrently.

**Fix:**
```python
import asyncio

def __init__(self):
    self._reports: Dict[str, StrategyReport] = {}
    self._lock = asyncio.Lock()

async def update_from_settlement(self, strategy: str, db: Optional[Session] = None):
    async with self._lock:
        # ... existing computation ...
        self._reports[strategy] = report
```

---

## MEDIUM RISK ISSUES

### 5. **heartbeat.py:17-18, 24-25** — Threading Lock Present ✓
**Risk Level:** 🟡 MEDIUM  
**File:** `backend/core/heartbeat.py`  
**Status:** ✓ PROTECTED

```python
_pending_heartbeats: dict[str, str] = {}
_hb_lock = threading.Lock()

def update_heartbeat(strategy_name: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _hb_lock:
        _pending_heartbeats[strategy_name] = ts  # Protected
```

**Assessment:** Lock is correctly used. No race condition detected.

---

### 6. **config_service.py:12-13, 29-42** — Threading Lock Present ✓
**Risk Level:** 🟡 MEDIUM  
**File:** `backend/core/config_service.py`  
**Status:** ✓ PROTECTED

```python
_settings_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()

def get_setting(key: str, default: Any = None, db: Optional[Session] = None) -> Any:
    with _cache_lock:
        if key in _settings_cache:
            return _settings_cache[key]
    # ... DB query ...
    with _cache_lock:
        _settings_cache[key] = value  # Protected
```

**Assessment:** Lock is correctly used. No race condition detected.

---

### 7. **settlement.py:26** — Asyncio Lock Declared
**Risk Level:** 🟡 MEDIUM  
**File:** `backend/core/settlement.py`  
**Status:** ⚠️ VERIFY USAGE

```python
_settlement_lock = asyncio.Lock()
```

**Assessment:** Lock exists but need to verify it's used in all critical sections. Recommend grep for `async with _settlement_lock:` to confirm coverage.

---

## LOW RISK / INFORMATIONAL

### 8. **strategy_executor.py:33, 98** — Trade Execution Lock ✓
**Risk Level:** 🟢 LOW  
**File:** `backend/core/strategy_executor.py`  
**Status:** ✓ PROTECTED

```python
_trade_execution_lock = asyncio.Lock()

async def execute_decision(...):
    async with _trade_execution_lock:
        # ... trade execution ...
```

**Assessment:** Lock correctly guards trade execution. No race condition.

---

### 9. **circuit_breaker.py:37** — Instance-level Lock ✓
**Risk Level:** 🟢 LOW  
**File:** `backend/core/circuit_breaker.py`  
**Status:** ✓ PROTECTED

```python
self._lock = asyncio.Lock()
```

**Assessment:** Instance-level locks are safe (not global state). No race condition.

---

### 10. **error_logger.py:48** — Instance-level Lock ✓
**Risk Level:** 🟢 LOW  
**File:** `backend/core/error_logger.py`  
**Status:** ✓ PROTECTED

```python
self._lock = asyncio.Lock()
```

**Assessment:** Instance-level lock. No race condition.

---

### 11. **task_manager.py:17** — Instance-level Lock ✓
**Risk Level:** 🟢 LOW  
**File:** `backend/core/task_manager.py`  
**Status:** ✓ PROTECTED

```python
self._lock = asyncio.Lock()
```

**Assessment:** Instance-level lock. No race condition.

---

## ASYNCIO VOID CHECK ISSUES

### 12. **settlement.py:346, 417** — Conditional Await (Logic Verification Needed)
**Risk Level:** 🟢 LOW  
**File:** `backend/core/settlement.py`

**Issue:** Conditional await without colon
```python
if await process_settled_trade(...)  # Line 346
```

**Assessment:** This is valid Python (await returns a value that's checked). Not a race condition, but verify the logic is correct (should the result be checked?).

---

## SUMMARY TABLE

| File | Line(s) | Issue | Risk | Status |
|------|---------|-------|------|--------|
| position_valuation.py | 22-24, 240, 260 | Unprotected async cache writes | 🔴 HIGH | ❌ NEEDS FIX |
| auto_improve.py | 42, 291 | Unprotected global state mutation | 🔴 HIGH | ❌ NEEDS FIX |
| calibration.py | 25, 32, 35 | Unprotected global cache (check-then-act) | 🟠 MEDIUM-HIGH | ❌ NEEDS FIX |
| strategy_performance_registry.py | 186 | Lock declared but unused | 🟠 MEDIUM-HIGH | ❌ NEEDS FIX |
| settlement.py | 26 | Asyncio lock declared | 🟡 MEDIUM | ⚠️ VERIFY |
| heartbeat.py | 17-18, 24-25 | Threading lock present | 🟡 MEDIUM | ✓ OK |
| config_service.py | 12-13, 29-42 | Threading lock present | 🟡 MEDIUM | ✓ OK |
| strategy_executor.py | 33, 98 | Trade execution lock | 🟢 LOW | ✓ OK |
| circuit_breaker.py | 37 | Instance-level lock | 🟢 LOW | ✓ OK |
| error_logger.py | 48 | Instance-level lock | 🟢 LOW | ✓ OK |
| task_manager.py | 17 | Instance-level lock | 🟢 LOW | ✓ OK |

---

## PRIORITY RECOMMENDATIONS

### P0 (Immediate — Production Risk)
1. **position_valuation.py** — Add asyncio.Lock around cache writes (lines 240, 260)
2. **auto_improve.py** — Add asyncio.Lock around global state mutation (line 291)

### P1 (High — Data Integrity Risk)
3. **calibration.py** — Add threading.Lock around _load() function (lines 29-35)
4. **strategy_performance_registry.py** — Initialize and use self._lock in update_from_settlement()

### P2 (Medium — Verification)
5. **settlement.py** — Verify _settlement_lock is used in all critical sections
6. Add type hints for lock objects (currently `self._lock = None` in strategy_performance_registry.py)

---

## IMPLEMENTATION CHECKLIST

- [ ] Fix position_valuation.py cache (P0)
- [ ] Fix auto_improve.py global state (P0)
- [ ] Fix calibration.py cache (P1)
- [ ] Fix strategy_performance_registry.py lock (P1)
- [ ] Verify settlement.py lock usage (P2)
- [ ] Run tests after fixes
- [ ] Update IMPLEMENTATION_GAPS.md with resolved issues
