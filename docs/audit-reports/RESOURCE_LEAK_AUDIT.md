# Resource Leak Audit Report
**Generated**: 2026-05-03  
**Auditor**: Kiro (Sisyphus-Junior)

## Executive Summary

Comprehensive audit of resource management across the polyedge codebase. Identified **4 critical leak patterns** affecting HTTP clients, WebSocket connections, and database sessions.

---

## 🔴 CRITICAL: Unclosed HTTP Clients

### 1. `backend/sources/polymarket_book.py:32`
**Severity**: HIGH  
**Pattern**: `httpx.AsyncClient` created but never closed

```python
30:     async def _get_client(self) -> httpx.AsyncClient:
31:         if self._client is None:
32:             self._client = httpx.AsyncClient(timeout=10.0)
33:         return self._client
```

**Issue**: Client is cached in `self._client` but never closed. No `aclose()` call in class lifecycle.

**Impact**: Connection pool exhaustion, file descriptor leak, memory leak over time.

**Fix Required**: Add cleanup method:
```python
async def close(self):
    if self._client:
        await self._client.aclose()
        self._client = None
```

---

### 2. `backend/strategies/copy_trader.py:99-112`
**Severity**: MEDIUM (has cleanup, but risky pattern)  
**Pattern**: `httpx.AsyncClient` created in `start()`, closed in `stop()`

```python
98:     async def start(self):
99:         self._http = httpx.AsyncClient(
100:             timeout=httpx.Timeout(15.0),
101:             limits=httpx.Limits(max_keepalive_connections=5),
102:         )
...
109:     async def stop(self):
110:         self._running = False
111:         if self._http:
112:             await self._http.aclose()
```

**Issue**: Relies on explicit `stop()` call. If exception occurs before `stop()`, client leaks.

**Recommendation**: Use context manager pattern or ensure `stop()` is called in `finally` block.

---

### 3. `backend/strategies/whale_pnl_tracker.py:57` & `89`
**Severity**: LOW (has cleanup logic)  
**Pattern**: Conditional client creation with manual cleanup

```python
52: async def _fetch_token_id(
53:     condition_id: str, http: Optional[httpx.AsyncClient] = None
54: ) -> Optional[str]:
55:     close_client = False
56:     if http is None:
57:         http = httpx.AsyncClient(timeout=10.0)
58:         close_client = True
59:     try:
60:         resp = await http.get(...)
...
79:     finally:
80:         if close_client:
81:             await http.aclose()
```

**Status**: ✅ Properly handled with `finally` block.

**Same pattern in**:
- `backend/strategies/copy_trader.py:37` (lines 32-62)
- `backend/strategies/whale_pnl_tracker.py:89` (lines 84-101)

---

## 🟡 MEDIUM: WebSocket Connection Management

### 4. `backend/data/whale_monitor_ws.py:43`
**Severity**: MEDIUM  
**Pattern**: WebSocket created without guaranteed cleanup

```python
40:     async def connect(self) -> bool:
41:         try:
42:             self._ws = await websockets.connect(WHALE_WS_URL, ping_interval=10)
43:             self._running = True
...
52:     async def disconnect(self) -> None:
53:         self._running = False
54:         if self._ws:
55:             try:
56:                 await self._ws.close()
57:             except Exception:
58:                 pass
```

**Issue**: `disconnect()` must be explicitly called. No context manager usage.

**Recommendation**: Wrap in async context manager or ensure `disconnect()` is called in cleanup.

---

### 5. `backend/data/orderbook_hft_ws.py:37`
**Severity**: MEDIUM  
**Pattern**: Same as whale_monitor_ws

```python
36:             import websockets
37:             self._ws = await websockets.connect(OB_WS_URL, ping_interval=30)
38:             self._running = True
...
45:     async def disconnect(self) -> None:
46:         self._running = False
47:         if self._ws:
48:             try:
49:                 await self._ws.close()
```

**Issue**: Same pattern — requires explicit `disconnect()` call.

---

### 6. `backend/data/polygon_listener.py:33`
**Severity**: LOW  
**Pattern**: WebSocket used with context manager ✅

```python
33:                 async with websockets.connect(self.ws_url) as ws:
34:                     self._ws = ws
...
42:                     async for msg in ws:
43:                         await self._handle_message(msg)
```

**Status**: ✅ Properly handled with `async with` context manager.

---

### 7. `backend/data/polymarket_websocket.py:207`
**Severity**: LOW  
**Pattern**: WebSocket used with context manager ✅

```python
207:         async with websockets.connect(uri) as ws:
208:             self.ws = ws
...
226:                 async for message in ws:
227:                     await self._handle_message(message)
```

**Status**: ✅ Properly handled with `async with` context manager.

---

## 🟢 LOW: Database Sessions (Test Files Only)

### Pattern: `Session()` without context manager in tests

**Files affected** (all in `backend/tests/`):
- `test_quant_platform.py:20`
- `test_proposal_applier.py:32`
- `test_database_integrity.py:72, 106, 153, 181, 204, 224`
- `test_wallet_reconciliation_e2e.py:40`
- `test_alert_manager.py:24`
- `test_backtester.py:32`
- `test_error_logger.py:18`
- `test_audit_integration.py:15`
- `conftest_agi.py:34`
- `test_stats_correlator.py:17`
- `test_kg_models.py:22`
- `test_allocation_enforcement.py:31`
- `test_position_valuation.py:49`
- `test_proposal_executor.py:36`

**Severity**: LOW (test code, short-lived processes)

**Issue**: Test sessions created without `with` statement or explicit `.close()`.

**Recommendation**: Refactor to use context manager:
```python
# Before
session = Session()
# ... test code ...

# After
with Session() as session:
    # ... test code ...
```

---

## ✅ SAFE: File Handles

All `open()` calls use context managers (`with open(...) as f:`). No leaks detected.

**Files checked**:
- `backend/ai/training/train.py:59, 117`
- `backend/ai/training/model_trainer.py:62, 90`
- `backend/ai/strategy_composer.py:220`
- `backend/ai/logger.py:102, 174`
- `backend/ai/prediction_engine.py:65`
- `backend/core/risk_profiles.py:291, 305`
- `backend/core/nightly_review.py:47`
- `backend/api/admin.py:214, 228`

---

## Priority Fix List

### 🔴 CRITICAL (Fix Immediately)
1. **`backend/sources/polymarket_book.py`** — Add `close()` method and lifecycle management

### 🟡 MEDIUM (Fix Soon)
2. **`backend/strategies/copy_trader.py`** — Ensure `stop()` is called in exception paths
3. **`backend/data/whale_monitor_ws.py`** — Add context manager or ensure cleanup
4. **`backend/data/orderbook_hft_ws.py`** — Add context manager or ensure cleanup

### 🟢 LOW (Refactor When Convenient)
5. **Test files** — Refactor to use `with Session() as session:` pattern

---

## Recommendations

### 1. Establish Resource Management Standards
- **HTTP Clients**: Always use `async with httpx.AsyncClient() as client:` for short-lived requests
- **Long-lived clients**: Implement explicit lifecycle (`start()`/`stop()`) with guaranteed cleanup
- **WebSockets**: Prefer `async with websockets.connect() as ws:` pattern
- **Database Sessions**: Always use `with Session() as session:` or FastAPI dependency injection

### 2. Add Linting Rules
Consider adding `ruff` or `pylint` rules to detect:
- `httpx.AsyncClient()` without corresponding `aclose()`
- `Session()` without context manager
- `websockets.connect()` without context manager

### 3. Add Cleanup Tests
Add integration tests that verify resource cleanup:
```python
async def test_resource_cleanup():
    tracker = CopyTrader(...)
    await tracker.start()
    # Simulate exception
    try:
        raise Exception("test")
    finally:
        await tracker.stop()
    # Verify no leaked connections
```

---

## Conclusion

**Total Issues**: 7  
**Critical**: 1  
**Medium**: 3  
**Low**: 3  

Primary concern is the unclosed `httpx.AsyncClient` in `polymarket_book.py`. Other issues are manageable with proper lifecycle management and exception handling.

**Estimated Fix Time**: 2-4 hours  
**Risk Level**: Medium (production stability impact if not addressed)
