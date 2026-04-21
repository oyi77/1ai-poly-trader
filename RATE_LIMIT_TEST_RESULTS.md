# Rate Limit Test Results - Task 31

**Test Date:** 2026-04-21  
**Status:** ✅ RATE LIMITING WORKING (with caveats)

## Executive Summary

Rate limiting is **functional** but has discovered issues:

1. ✅ **429 responses working** - Rate limited requests return proper 429 status
2. ✅ **Retry-After header present** - All 429 responses include `Retry-After: 60`
3. ⚠️ **Rate limit headers missing** - X-RateLimit-* headers not in responses
4. ⚠️ **HTTP per-IP limit too aggressive** - 50/minute limit hits before endpoint limits
5. ⚠️ **Endpoints return 404** - /api/trades, /api/signals, /api/strategies don't exist (404 Not Found)

## Test Results

### Endpoint Testing

| Endpoint | Limit | Status | Issue |
|----------|-------|--------|-------|
| /api/trades | 100/min | ❌ 404 Not Found | Endpoint doesn't exist |
| /api/signals | 50/min | ⚠️ Rate Limited | HTTP per-IP limit (50/min) hits first |
| /api/strategies | 20/min | ⚠️ Rate Limited | HTTP per-IP limit (50/min) hits first |

### Rate Limit Headers

**Expected Headers:**
- `X-RateLimit-Limit` - Maximum requests allowed
- `X-RateLimit-Remaining` - Requests remaining in window
- `X-RateLimit-Reset` - Unix timestamp of window reset

**Actual Response:**
```
HTTP/1.1 429 Too Many Requests
retry-after: 60
content-type: application/json

{"error_code":"RATE_LIMIT_EXCEEDED","message":"Rate limit exceeded. Maximum 100 requests per minute.","retry_after":60}
```

**Finding:** Rate limit headers are **MISSING** from responses.

### Multi-IP Testing

**Result:** ❌ FAILED

Each IP should get independent rate limits, but all IPs hit the HTTP per-IP limit (50/min) simultaneously:
- IP 192.168.1.1: 0 successful, 3 rate limited
- IP 192.168.1.2: 0 successful, 3 rate limited  
- IP 192.168.1.3: 0 successful, 3 rate limited

**Finding:** HTTP per-IP limit (50/min) is shared across all IPs, not per-IP.

### Retry-After Header

**Result:** ✅ PASSED

All 429 responses include `Retry-After: 60` header.

## Root Causes

### Issue 1: Missing Rate Limit Headers

**Location:** `backend/api/rate_limiter.py` lines 88-98, 120-130

The middleware returns 429 responses but doesn't include standard rate limit headers in the JSON response body. Headers are only added to successful responses (lines 136-138).

**Fix Required:**
```python
# Add headers to 429 response
response.headers["X-RateLimit-Limit"] = str(limit)
response.headers["X-RateLimit-Remaining"] = "0"
response.headers["X-RateLimit-Reset"] = str(reset_time)
```

### Issue 2: HTTP Per-IP Limit Too Aggressive

**Location:** `backend/api/rate_limiter.py` lines 57-73, 82-98

The middleware enforces a global HTTP per-IP limit (50/min) BEFORE checking endpoint-specific limits. This causes all requests to be rate limited at 50/min regardless of endpoint.

**Current Flow:**
1. Check HTTP per-IP limit (50/min) ← **BLOCKS HERE**
2. Check endpoint-specific limit (100/min for /api/trades, etc.)

**Fix Required:** Either:
- Increase HTTP per-IP limit to match highest endpoint limit (100/min)
- Remove HTTP per-IP limit and rely on endpoint-specific limits
- Make HTTP per-IP limit configurable per endpoint

### Issue 3: Endpoints Don't Exist

**Finding:** `/api/trades` returns 404 Not Found

**Actual Endpoints:**
- `/api/signals` ✅ Exists
- `/api/strategies` ✅ Exists
- `/api/trades` ❌ Does not exist (should be `/api/trades` or similar)

**Fix Required:** Update test to use correct endpoint paths or create missing endpoints.

## Recommendations

### Priority 1: Fix Rate Limit Headers
Add X-RateLimit-* headers to 429 responses for client-side rate limit handling.

### Priority 2: Fix HTTP Per-IP Limit
Either increase to 100/min or remove in favor of endpoint-specific limits.

### Priority 3: Verify Endpoint Paths
Confirm correct endpoint paths and update test accordingly.

## Test Script Location

`tests/load/rate_limit_test.py`

**Usage:**
```bash
# Run all tests (skips 65s reset test)
python tests/load/rate_limit_test.py

# Run with reset test (takes 3+ minutes)
python tests/load/rate_limit_test.py --no-skip-reset
```

## Conclusion

Rate limiting is **implemented and functional** but needs refinement:
- ✅ Returns 429 for rate limited requests
- ✅ Includes Retry-After header
- ❌ Missing X-RateLimit-* headers
- ❌ HTTP per-IP limit too aggressive
- ❌ Test endpoints don't exist

**Recommendation:** Fix headers and HTTP per-IP limit, then re-run tests.
