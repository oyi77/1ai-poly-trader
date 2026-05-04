# API Endpoint Security & Rate Limiting Audit

**Date**: 2026-05-04
**Scope**: All FastAPI endpoints in `backend/api/` (22 router files)
**Total Endpoints**: 174

---

## Executive Summary

| Category | Count | Status |
|----------|-------|--------|
| Admin-protected endpoints | 90 | ✓ Secured with `require_admin` |
| Public read-only (GET) | 72 | ℹ️ Lower risk — consider rate limiting |
| Public write (POST/PUT/DELETE) | 12 | ⚠️ High risk — no rate limit, some lack admin |
| **Critical unauthenticated** | **2** | 🔴 **CRITICAL — immediate fix required** |
| **High-risk unprotected admin ops** | **12+** | 🟠 **HIGH — fix within 24h** |

**Rate Limiting Status**: 0 of 174 endpoints have per-endpoint decorators. All rely on global in-process middleware (600 req/min), which is ineffective in multi-worker deployments and resets on restart.

---

## 🔴 CRITICAL GAPS — Immediate Action Required (< 24h)

### Unauthenticated Dangerous Operations

| Endpoint | File | Method | Risk |
|----------|------|--------|------|
| `POST /emergency-stop` | `backend/api/agi_routes.py` | Shuts down entire bot | System takeover / DoS |
| `POST /goal/override` | `backend/api/agi_routes.py` | Overrides AGI goal constraints | AGI safety boundary violation |

**Fix**: Add `Depends(require_admin)` to both endpoints immediately.

---

## 🟠 HIGH-RISK GAPS — Fix This Week

### Unprotected Admin Operations

| Endpoint | File | Expected Protection |
|----------|------|---------------------|
| `GET /settings`, `POST /settings` | `backend/api/admin.py` | `require_admin` |
| `GET /system` | `backend/api/admin.py` | `require_admin` |
| `GET /system/audit-logs` | `backend/api/system.py` | `require_admin` |
| `GET /system/errors` | `backend/api/system.py` | `require_admin` |
| `GET /trade-attempts` | `backend/api/system.py` | `require_admin` |
| `POST /proposals/generate` | `backend/api/proposals.py` | `require_admin` |
| `GET /wallet/active`, `PUT /wallet/active` | `backend/api/wallets.py` | `require_admin` |
| `POST /strategies/compose` | `backend/api/agi_routes.py` | `require_admin` |
| `POST /counterfactual/run` | `backend/api/agi_routes.py` | `require_admin` |

### Public Write Endpoints (Lacking Rate Limits)

All POST/PUT/DELETE endpoints on public-facing routes lack per-endpoint rate limits, enabling abuse:
- `/api/proposals/*` (write)
- `/api/wallets/*` (write)
- `/api/markets/*` (some write)
- `/api/settings/*` (some write)

---

## 📊 Rate Limiting Posture — Systemic Failure

### Current Implementation

`backend/api/rate_limiter.py` defines in-process limiter using `slowapi.Limiter` with memory store:
```python
limiter = Limiter(key_func=get_remote_address, default_limits=["600/minute"])
```

**Problems:**
1. **No per-endpoint decorators** — all 174 endpoints use only global default
2. **In-process memory store** — counters reset on restart; ineffective for production
3. **Multi-worker bypass** — each worker process has independent counter → 4 workers = 4× effective limit
4. **No Redis backing** — cannot share state across horizontally scaled instances

### Configured but Unenforced Limits

`backend/api/main.py` middleware configuration includes:
- `/api/trades`: 100/min (configured only, no decorator)
- `/api/signals`: 50/min (configured only)
- `/api/strategies`: 20/min (configured only)

These have **no effect** without `@limiter.limit()` decorators on the endpoint functions.

---

## 🔧 Recommended Fixes (Priority Order)

### IMMEDIATE (24 hours)
1. **Add `require_admin` to 2 CRITICAL endpoints** in `agi_routes.py`:
   - `emergency_stop()`
   - `override_goal()`
2. **Add `require_admin` to all `/admin/*` endpoints** in `admin.py`
3. **Add `require_admin` to sensitive operations** in `wallets.py`, `system.py`, `proposals.py`

### HIGH (1 week)
4. **Replace in-process limiter with Redis-backed slowapi:**
   ```python
   from slowapi import Limiter
   from slowapi.util import get_remote_address
   from slowapi.errors import RateLimitExceeded
   import redis

   storage_uri = os.getenv("REDIS_URL", "redis://localhost:6379")
   limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
   ```
5. **Add per-endpoint `@limiter.limit()` decorators:**
   - Expensive ops (`/backtest`, `/counterfactual/run`): 10/min
   - Write ops (`/proposals/generate`, `/wallet/*`): 30/min
   - Market data (`/markets/*`): 100/min
   - Dashboard (`/dashboard`, `/health`): 600/min (already global)

### MEDIUM (2 weeks)
6. **Add audit logging** for all admin operations — who changed what and when
7. **Implement request signing** for sensitive operations (HMAC on payload + timestamp)
8. **Add CORS restrictions** per endpoint (frontend origins only for sensitive ops)
9. **Write integration tests** verifying admin dependency blocks unauthorized access

---

## Files Requiring Changes

| File | Endpoints Affected | Action |
|------|-------------------|--------|
| `backend/api/agi_routes.py` | `/emergency-stop`, `/goal/override`, `/strategies/compose`, `/counterfactual/run` | Add `require_admin` |
| `backend/api/admin.py` | All 3 endpoints | Add `require_admin` (may already have — verify) |
| `backend/api/wallets.py` | `/wallet/active` GET/PUT | Add `require_admin` |
| `backend/api/system.py` | `/system/audit-logs`, `/system/errors`, `/trade-attempts` | Add `require_admin` |
| `backend/api/proposals.py` | `/proposals/generate` POST | Add `require_admin` |
| `backend/api/rate_limiter.py` | All | Replace memory store with Redis |
| `backend/api/main.py` | Middleware setup | Add per-endpoint decorators |

---

*Report generated: 2026-05-04 — 174 endpoints audited across 22 API router files*
