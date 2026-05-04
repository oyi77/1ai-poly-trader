# Circuit Breaker Usage Verification

**Date**: 2026-05-04
**Scope**: 6 target files for external API/WebSocket call protection
**Files**: `backend/data/kalshi_client.py`, `backend/data/goldsky_client.py`, `backend/data/gamma.py`, `backend/core/market_scanner.py`, `backend/core/monitoring.py`, `backend/data/polymarket_scraper.py`

---

## Executive Summary

| File | HTTP Calls Found | Protected | Unprotected | Coverage |
|------|-----------------|-----------|-------------|----------|
| `kalshi_client.py` | 1 | ✅ 1 | ❌ 0 | **100%** |
| `goldsky_client.py` | 1 | ❌ 0 | ✅ 1 | **0%** |
| `gamma.py` | 2 | ❌ 0 | ✅ 2 | **0%** |
| `market_scanner.py` | 1 | ❌ 0 | ✅ 1 | **0%** |
| `monitoring.py` | 2 | ❌ 0 | ✅ 2 | **0%** |
| `polymarket_scraper.py` | 0 | — | — | N/A |

**Overall**: 1 of 7 calls protected (14% coverage). **6 critical gaps**.

---

## Protected Call (Example Pattern)

### `backend/data/kalshi_client.py:80` — Kalshi GET markets

```python
async def _fetch():
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

return await kalshi_breaker.call(_fetch)
```

Breaker: `kalshi_breaker = CircuitBreaker("kalshi", failure_threshold=5, recovery_timeout=60.0)`

---

## 🔴 Unprotected Calls (Critical Gaps)

### 1. `backend/data/goldsky_client.py:68` — Goldsky GraphQL POST

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.post(GOLDSKY_URL, json=payload)
    resp.raise_for_status()
    data = resp.json()
# ❌ No breaker wrapper
```

**Operation**: `orderFilledEvents` — retrieves whale order fills for trader analytics.
**Risk**: Goldsky outage → unhandled exception bubbles up → whale strategy stalls silently.
**Fix**: Wrap with `goldsky_breaker.call(_fetch)` — create breaker in `circuit_breaker_pybreaker.py`.

---

### 2. `backend/data/gamma.py:43` — Gamma API fetch_markets GET

```python
async with httpx.AsyncClient(timeout=15.0) as client:
    resp = await client.get(GAMMA_API_URL, params={...})
    resp.raise_for_status()
    data = resp.json()
# ❌ No breaker wrapper
```

**Operation**: `fetch_markets` — discovers active Polymarket markets.
**Risk**: Gamma outage → active market discovery fails → scanner has no markets to process.
**Fix**: Wrap with `polymarket_breaker.call(_fetch)` (existing breaker in `btc_markets.py`).

---

### 3. `backend/data/gamma.py:99` — Gamma API fetch_resolved_markets GET

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    resp = await client.get(f"{GAMMA_API_URL}/markets/resolved", params={...})
    resp.raise_for_status()
    data = resp.json()
# ❌ No breaker wrapper
```

**Operation**: `fetch_resolved_markets` — fetches historical market outcomes for backtesting and calibration.
**Risk**: Gamma outage → backtesting pipeline blocked; settlement cannot verify outcomes.
**Fix**: Wrap with `polymarket_breaker.call(_fetch)`.

---

### 4. `backend/core/market_scanner.py:143` — Gamma scan GET

```python
async with httpx.AsyncClient(timeout=15.0) as client:
    resp = await client.get(GAMMA_SCAN_URL, params=params)
    resp.raise_for_status()
    all_markets = resp.json()
# ❌ No breaker wrapper
```

**Operation**: `fetch_all_active_markets` — market scanner's primary data source.
**Risk**: Gamma outage → scanner crashes → no new signals generated system-wide.
**Fix**: Wrap with `polymarket_breaker.call(_fetch)` or create `gamma_breaker`.

---

### 5. `backend/core/monitoring.py:213` — Slack webhook alert POST

```python
async with httpx.AsyncClient(timeout=10.0) as client:
    await client.post(SLACK_WEBHOOK_URL, json=payload)
# ❌ No breaker wrapper
```

**Operation**: `send_slack_alert` — operational alerting to Slack.
**Risk**: Slack webhook down (rate limit, 5xx) → exception raised → alert loss; but should not crash bot.
**Fix**: Wrap with `webhook_breaker.call_safe(_send, fallback=lambda: None)` — non-critical, fail silently.

---

### 6. `backend/core/monitoring.py:239` — Discord webhook alert POST

```python
async with httpx.AsyncClient(timeout=10.0) as client:
    await client.post(DISCORD_WEBHOOK_URL, json=payload)
# ❌ No breaker wrapper
```

**Operation**: `send_discord_alert` — operational alerting to Discord.
**Risk**: Discord webhook down → alert loss.
**Fix**: Wrap with `webhook_breaker` same as Slack.

---

## Cascade Risk Analysis

**Scenario: Gamma API outage (affects 3 unprotected calls)**
1. `gamma.py:fetch_markets` fails → active market list empty
2. `gamma.py:fetch_resolved_markets` fails → settlement can't verify outcomes
3. `market_scanner.py:fetch_all_active_markets` fails → scanner raises exception → scheduler job error → no signals
**Result**: Trading halts with no immediate alert (monitoring webhooks also unprotected).

**Scenario: Goldsky outage**
- `goldsky_client.py:fetch_order_filled_events` fails → whale tracking stops → copy-trader and whale-frontrun strategies lose signal source.
- No breaker → repeated retries flood Goldsky with traffic during outage.

---

## Existing Breakers (Unused in Target Files)

Breakers defined in `backend/data/btc_markets.py` and `backend/data/polymarket_clob.py`:

| Breaker | Target | Status |
|---------|--------|--------|
| `polymarket_breaker` | Polymarket Gamma / CLOB | ✅ Available, not used in `gamma.py` or `market_scanner.py` |
| `kalshi_breaker` | Kalshi API | ✅ In use in `kalshi_client.py` |
| Custom in `btc_markets.py` | Coinbase/Kraken/Binance | ✅ In use |

---

## Implementation Checklist

- [ ] Add `goldsky_breaker = CircuitBreaker("goldsky", failure_threshold=5, recovery_timeout=60.0)` to `circuit_breaker_pybreaker.py`
- [ ] Wrap `goldsky_client.py:68` with `return await goldsky_breaker.call(_fetch)`
- [ ] Wrap `gamma.py:43` with `return await polymarket_breaker.call(_fetch)` (reuse existing)
- [ ] Wrap `gamma.py:99` with `return await polymarket_breaker.call(_fetch)`
- [ ] Wrap `market_scanner.py:143` with `return await polymarket_breaker.call(_fetch)`
- [ ] Add `webhook_breaker = CircuitBreaker("webhooks", failure_threshold=3, recovery_timeout=120.0)` (lower threshold, longer timeout)
- [ ] Wrap `monitoring.py:213` and `monitoring.py:239` with `await webhook_breaker.call_safe(_send, fallback=lambda: None)`
- [ ] Write unit tests confirming breaker opens after threshold failures and recovers after timeout

---

*Report generated: 2026-05-04 — 7 HTTP calls audited across 5 files; 6 unprotected (14% coverage)*
