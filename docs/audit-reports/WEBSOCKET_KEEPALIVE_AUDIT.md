# WebSocket Keep-Alive Configuration Audit

**Date**: 2026-05-04
**Scope**: All `websockets.connect()` calls in `backend/`
**Total Calls Found**: 6

---

## Executive Summary

| Status | Count | Files |
|--------|-------|-------|
| Fully Protected (ping_interval + ping_timeout) | 2 | `ws_client.py`, `orderbook_ws.py` |
| Partially Protected (ping_interval only) | 2 | `orderbook_hft_ws.py`, `whale_monitor_ws.py` |
| **Critical Gaps** (no heartbeat) | **2** | **`polygon_listener.py`**, **`polymarket_websocket.py`** |

---

## Detailed findings

### ✅ Fully Protected

| File | Line | Configuration |
|------|------|---------------|
| `backend/data/ws_client.py` | 162 | `ping_interval=30.0`, `ping_timeout=10` |
| `backend/data/orderbook_ws.py` | 209 | `ping_interval=30.0`, `ping_timeout=10` |

### ⚠️ Partially Protected (uses default ping_timeout=20s)

| File | Line | Configuration |
|------|------|---------------|
| `backend/data/orderbook_hft_ws.py` | 37 | `ping_interval=30` only |
| `backend/data/whale_monitor_ws.py` | 43 | `ping_interval=10` only |

### 🔴 Critical Gaps (no heartbeat protection)

| File | Line | Risk |
|------|------|------|
| `backend/data/polygon_listener.py` | 207 | Silent disconnection → stale BTC price feed |
| `backend/data/polymarket_websocket.py` | 33 | Silent disconnection → stale order book / trades |

---

## Cross-validation

✅ Findings match `NETWORK_RESILIENCE_AUDIT.md` lines 11–17 exactly. No additional gaps found.

---

## Recommended Fix

Add to both critical gaps:
```python
websockets.connect(
    url,
    ping_interval=30.0,   # send ping every 30s
    ping_timeout=10.0,    # wait 10s for pong before considering dead
)
```

Consistent with fully-protected calls in `ws_client.py` and `orderbook_ws.py`.
