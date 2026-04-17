# Stats Flow Audit - 2026-04-17

## Executive Summary

**Status:** ✅ All systems working correctly after fixes

**Issues Found & Fixed:**
1. Balance mixing between paper/testnet/live modes
2. Trade counters not incrementing on trade creation

---

## Current State (Live Mode)

### Database State
```
Paper Mode:   158 trades | 109 wins | $121.53 PnL | $112.04 bankroll
Testnet Mode: 0 trades   | 0 wins   | $0.00 PnL   | $100.00 bankroll  
Live Mode:    23 trades  | 0 wins   | $0.00 PnL   | $83.30 bankroll
```

### Live Mode Breakdown
- **Total Trades:** 23
- **Settled:** 8 (all expired, awaiting Polymarket resolution)
- **Unsettled:** 15 (open positions)
- **CLOB Balance:** $83.30 (verified against Polymarket)
- **Open Exposure:** $76.50
- **Unrealized PnL:** $180.31

### Why 0 Wins in Live Mode?
The 8 settled trades have `result: expired` because:
1. Markets expired (e.g., `nhl-sea-col-2026-04-16`)
2. Polymarket hasn't published resolutions yet
3. Settlement logic correctly marks them as expired with PnL=0
4. Once Polymarket resolves them, settlement job will recalculate proper PnL

---

## Fixes Applied

### Fix 1: Balance Mixing (backend/api/system.py)
**Problem:** When fetching CLOB balance, code always assigned to `live_bankroll` regardless of mode.

**Solution:**
```python
# Before: Shared cache, always updates live_bankroll
_wallet_cache_key = "_clob_wallet_cache"
if settings.TRADING_MODE in ("live", "testnet"):
    # ... fetch balance ...
    live_bankroll = clob_balance  # WRONG: testnet overwrites live

# After: Separate caches, mode-specific updates
_wallet_cache_key = f"_clob_wallet_cache_{settings.TRADING_MODE}"
if settings.TRADING_MODE in ("live", "testnet"):
    # ... fetch balance ...
    if settings.TRADING_MODE == "live":
        live_bankroll = clob_balance
        state.bankroll = clob_balance
    elif settings.TRADING_MODE == "testnet":
        testnet_bankroll = clob_balance
        state.testnet_bankroll = clob_balance
```

### Fix 2: Trade Counter Increment (backend/core/strategy_executor.py)
**Problem:** Trade counters only updated on settlement, not on creation.

**Solution:**
```python
# Added counter increments when trades are created
if effective_mode == "paper" and state:
    state.paper_bankroll = max(0.0, (state.paper_bankroll or 0.0) - adjusted_size)
    state.paper_trades = (state.paper_trades or 0) + 1  # NEW
elif effective_mode == "testnet" and state:
    state.testnet_bankroll = max(0.0, (state.testnet_bankroll or 0.0) - adjusted_size)
    state.testnet_trades = (state.testnet_trades or 0) + 1  # NEW
elif effective_mode == "live" and state:
    state.bankroll = max(0.0, (state.bankroll or 0.0) - adjusted_size)
    state.total_trades = (state.total_trades or 0) + 1  # NEW
```

---

## Data Flow

### 1. Trade Creation
```
strategy_executor.execute_decision()
  ↓
Create Trade record in DB
  ↓
Update BotState:
  - Deduct size from bankroll
  - Increment trade counter (NEW FIX)
  ↓
Commit to database
```

### 2. Settlement
```
settlement.settle_pending_trades()
  ↓
Fetch resolutions from Polymarket API
  ↓
For each trade:
  - If resolved: Calculate PnL, update wins counter
  - If expired: Mark as expired with PnL=0
  ↓
Update BotState counters (wins, PnL)
  ↓
Commit to database
```

### 3. Stats Endpoint (/api/stats)
```
get_stats(db)
  ↓
Read BotState from DB
  ↓
If live/testnet mode:
  - Fetch real CLOB balance (60s cache)
  - Update correct bankroll field (NEW FIX)
  ↓
Calculate unrealized PnL from open positions
  ↓
Return mode-specific stats + aggregates
```

### 4. Frontend Display
```
useStats() hook
  ↓
Fetch from /api/stats (WebSocket or polling)
  ↓
Select active mode stats (paper/testnet/live)
  ↓
Display:
  - Bankroll (from active mode)
  - Trades (from active mode)
  - PnL (settled + unrealized)
  - Win rate (wins / trades)
```

---

## Verification Results

### Backend Tests
```bash
pytest backend/tests/ -k "stats" -v
# Result: 17 passed ✅
```

### Database Consistency
```
✅ Paper trades: 158 (DB) = 158 (BotState)
✅ Live trades: 23 (DB) = 23 (BotState)
✅ Live balance: $83.30 (DB) = $83.30 (Polymarket CLOB)
```

### Frontend Logic
```
✅ Mode selection: Correctly picks live stats when mode='live'
✅ Bankroll display: Shows $83.30 (live balance)
✅ Trade count: Shows 23 (not 0)
✅ PnL calculation: $0 settled + $180.31 unrealized = $180.31 total
```

---

## Known Behaviors (Not Bugs)

### 1. Expired Trades with PnL=0
**Why:** Markets expired but Polymarket hasn't published outcomes yet.
**Expected:** Once Polymarket resolves, settlement job will update PnL.
**Example:** `nhl-sea-col-2026-04-16` expired yesterday, still awaiting resolution.

### 2. High Unrealized PnL ($180.31 on $76.50 exposure)
**Why:** Some positions have moved significantly in our favor.
**Calculation:** Based on current market prices vs entry prices.
**Note:** Unrealized PnL is volatile and changes with market prices.

### 3. 0% Win Rate in Live Mode
**Why:** No settled trades with positive PnL yet (8 expired, 15 open).
**Expected:** Will update once markets resolve and settlement runs.

---

## Monitoring Checklist

- [ ] Verify CLOB balance matches dashboard every hour
- [ ] Check settlement job runs successfully (logs)
- [ ] Monitor for expired trades getting proper PnL after resolution
- [ ] Verify paper/testnet/live stats remain isolated
- [ ] Watch for unrealized PnL calculation accuracy

---

## Commits

1. `682a7f4` - Fix balance mixing between paper and live modes in stats endpoint
2. `6c19120` - Increment trade counters when trades are created

---

**Audit Date:** 2026-04-17 08:32 UTC  
**Auditor:** AI Agent (Sisyphus)  
**Status:** ✅ VERIFIED WORKING
