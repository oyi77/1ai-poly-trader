# PolyEdge vs Polymarket Dashboard Verification Checklist

**Date:** 2026-04-17  
**Purpose:** Verify that trades and balance tracking on polyedge.aitradepulse.com matches Polymarket dashboard

---

## 1. Balance Tracking Verification

### Current Implementation
Your system tracks balances in **3 modes** (paper/testnet/live):

**Source:** `backend/api/system.py` - `get_stats()` endpoint

#### Paper Mode (Simulation)
- **Initial Bankroll:** `$10,000` (from `settings.INITIAL_BANKROLL`)
- **Tracking:** `BotState.paper_bankroll` + `BotState.paper_pnl`
- **Updates:** On trade settlement via `settlement.py`
- **Formula:** `bankroll = INITIAL_BANKROLL + realized_pnl - open_exposure`

#### Testnet Mode
- **Initial Bankroll:** `$100` (default)
- **Tracking:** `BotState.testnet_bankroll` + `BotState.testnet_pnl`
- **Live Sync:** Fetches real CLOB balance every 60s (cached)
- **Source:** Polymarket CLOB API via `clob.get_wallet_balance()`

#### Live Mode
- **Tracking:** `BotState.bankroll` + `BotState.total_pnl`
- **Live Sync:** Fetches real CLOB balance every 60s (cached)
- **Source:** Polymarket CLOB API via `clob.get_wallet_balance()`
- **Note:** Wallet balance is authoritative, NOT calculated from trades

### ✅ What to Check

1. **Live/Testnet Mode Balance**
   - [ ] Compare `polyedge.aitradepulse.com` displayed balance
   - [ ] Against Polymarket dashboard wallet balance
   - [ ] Should match within 60 seconds (cache refresh interval)
   - [ ] Check: `GET /api/stats` → `bankroll` field

2. **Balance Sync Issues**
   - [ ] Check backend logs for: `"Failed to fetch {mode} CLOB wallet balance"`
   - [ ] Verify CLOB credentials are configured correctly
   - [ ] Test: Force refresh by waiting 60+ seconds

3. **Paper Mode Balance**
   - [ ] Verify formula: `Initial ($10k) + Realized PnL - Open Exposure`
   - [ ] Check if expired/closed trades return stake correctly
   - [ ] Verify no double-counting of PnL

---

## 2. Trade Tracking Verification

### Current Implementation
Trades are stored in `Trade` table with these key fields:

**Source:** `backend/models/database.py` - `Trade` model

```python
- market_ticker: str          # Market identifier
- platform: str               # "polymarket" or "kalshi"
- direction: str              # "up"/"down" or "yes"/"no"
- entry_price: float          # Price when trade opened
- size: float                 # Position size in USD
- timestamp: datetime         # Trade execution time
- settled: bool               # Whether market resolved
- result: str                 # "win"/"loss"/"pending"/"expired"
- pnl: float                  # Profit/loss after settlement
- trading_mode: str           # "paper"/"testnet"/"live"
- strategy: str               # Strategy that generated signal
```

### Trade Settlement Process
**Source:** `backend/core/settlement.py` - `settle_pending_trades()`

1. **Fetches market resolutions** from Polymarket API
2. **Calculates PnL** based on outcome:
   - **Win:** `pnl = (size / entry_price) - size` (net profit)
   - **Loss:** `pnl = -size` (lose entire stake)
   - **Expired:** `pnl = 0` (stake returned, no trade counted)
3. **Updates BotState** with realized PnL
4. **Returns stake** to bankroll on settlement

### ✅ What to Check

1. **Trade Execution Matching**
   - [ ] Compare trade list on PolyEdge vs Polymarket
   - [ ] Check: Market ticker/slug matches
   - [ ] Check: Direction (YES/NO or UP/DOWN) matches
   - [ ] Check: Entry price matches
   - [ ] Check: Position size matches
   - [ ] Check: Timestamp matches (within seconds)

2. **Trade Settlement Matching**
   - [ ] For settled trades, verify:
     - [ ] Result (WIN/LOSS) matches actual outcome
     - [ ] PnL calculation is correct
     - [ ] Settlement timestamp matches
   - [ ] For pending trades, verify:
     - [ ] Still shows as "pending" on both platforms
     - [ ] Market hasn't resolved yet

3. **PnL Calculation Verification**
   - [ ] **Win Formula:** `shares = size / entry_price`, `pnl = shares - size`
   - [ ] **Loss Formula:** `pnl = -size`
   - [ ] Example: $100 @ 0.65 entry, market resolves YES
     - Shares: 100 / 0.65 = 153.85
     - PnL: 153.85 - 100 = +$53.85 ✅
   - [ ] Example: $100 @ 0.65 entry, market resolves NO
     - PnL: -$100 ✅

4. **Unrealized PnL (Open Positions)**
   **Source:** `backend/api/system.py` lines 181-254
   - [ ] System fetches current market prices from Gamma API
   - [ ] Calculates: `unrealized_pnl = position_market_value - position_cost`
   - [ ] Check if this matches Polymarket's unrealized P&L
   - [ ] Note: 60s cache, may lag slightly

---

## 3. Common Discrepancy Sources

### A. Timing Issues
- **Cache Lag:** Balance syncs every 60s, may show stale data
- **Settlement Delay:** Markets may resolve on Polymarket before PolyEdge checks
- **API Rate Limits:** Polymarket API may throttle requests

### B. Mode Confusion
- **Paper vs Live:** Ensure you're comparing the correct mode
- **Check:** `GET /api/stats` → `mode` field should be "live" or "testnet"
- **Frontend:** Verify `useStats.ts` is displaying the correct mode stats

### C. Expired Trades
- **PolyEdge Behavior:** Trades older than 48 hours without resolution → marked "expired", pnl=0
- **Polymarket:** May still show as open or settled differently
- **Check:** `backend/config.py` → `STALE_TRADE_HOURS = 48`

### D. Position Reconciliation
**Source:** `backend/core/settlement_helpers.py` - `reconcile_positions()`
- System periodically checks if positions exist on CLOB
- Closes trades in DB that no longer exist on-chain
- May cause discrepancies if manual trades made outside PolyEdge

---

## 4. Debugging Steps

### Step 1: Check Current Mode
```bash
# Check which mode is active
curl https://polyedge.aitradepulse.com/api/stats | jq '.mode'
```

### Step 2: Compare Balance
```bash
# Get PolyEdge balance
curl https://polyedge.aitradepulse.com/api/stats | jq '.bankroll'

# Compare with Polymarket wallet balance
# (Check Polymarket dashboard manually)
```

### Step 3: Compare Trade Count
```bash
# Get PolyEdge trades
curl https://polyedge.aitradepulse.com/api/trades?limit=1000 | jq 'length'

# Compare with Polymarket trade history count
```

### Step 4: Check Settlement Status
```bash
# Get pending trades
curl https://polyedge.aitradepulse.com/api/trades | jq '[.[] | select(.settled == false)]'

# Verify these markets are still open on Polymarket
```

### Step 5: Force Settlement Check
```bash
# Trigger manual settlement (requires admin auth)
curl -X POST https://polyedge.aitradepulse.com/api/settle-trades \
  -H "Authorization: Bearer YOUR_ADMIN_KEY"
```

### Step 6: Check Backend Logs
```bash
# Look for settlement errors
grep "Settlement" backend.log | tail -50

# Look for CLOB balance fetch errors
grep "Failed to fetch.*CLOB wallet balance" backend.log | tail -20

# Look for position reconciliation
grep "Position reconciliation" backend.log | tail -20
```

---

## 5. Known Limitations

1. **60-Second Cache:** Live balance may lag by up to 60 seconds
2. **Batch Settlement:** Settlements run on schedule (not real-time)
3. **API Deduplication:** Multiple trades on same market share one API call
4. **Stale Trade Expiry:** Trades >48hrs old without resolution → expired
5. **Manual Trades:** Trades made directly on Polymarket won't appear in PolyEdge

---

## 6. Quick Verification Script

Create this file to automate checks:

```bash
#!/bin/bash
# verify_sync.sh

echo "=== PolyEdge vs Polymarket Sync Check ==="
echo ""

# Get stats
STATS=$(curl -s https://polyedge.aitradepulse.com/api/stats)

echo "Mode: $(echo $STATS | jq -r '.mode')"
echo "Balance: $$(echo $STATS | jq -r '.bankroll')"
echo "Total Trades: $(echo $STATS | jq -r '.total_trades')"
echo "Winning Trades: $(echo $STATS | jq -r '.winning_trades')"
echo "Win Rate: $(echo $STATS | jq -r '.win_rate')%"
echo "Total PnL: $$(echo $STATS | jq -r '.total_pnl')"
echo "Open Trades: $(echo $STATS | jq -r '.open_trades')"
echo "Unrealized PnL: $$(echo $STATS | jq -r '.unrealized_pnl')"
echo ""

# Get recent trades
TRADES=$(curl -s https://polyedge.aitradepulse.com/api/trades?limit=10)
echo "Recent Trades:"
echo $TRADES | jq -r '.[] | "\(.timestamp) | \(.market_ticker) | \(.direction) | $\(.size) @ \(.entry_price) | \(.result)"'
echo ""

echo "Now compare these values with your Polymarket dashboard!"
```

---

## 7. Expected Behavior Summary

### ✅ What SHOULD Match
- **Live/Testnet wallet balance** (within 60s)
- **Trade execution records** (ticker, direction, size, entry price)
- **Settled trade outcomes** (win/loss/expired)
- **Realized PnL** for settled trades
- **Open position count**

### ⚠️ What MAY Differ Slightly
- **Unrealized PnL** (60s cache lag on prices)
- **Settlement timing** (batch process vs real-time)
- **Expired trades** (PolyEdge auto-expires after 48hrs)

### ❌ What WON'T Match
- **Paper mode** (simulation only, not on Polymarket)
- **Manual Polymarket trades** (not tracked by PolyEdge)
- **Trades from other bots/wallets**

---

## Next Steps

1. **Run the verification script** above
2. **Compare side-by-side** with Polymarket dashboard
3. **Document any discrepancies** with:
   - Trade ID
   - Market ticker
   - Expected vs actual values
   - Screenshots from both platforms
4. **Check backend logs** for errors
5. **Report findings** with specific examples

---

**Questions to Answer:**
- Which trading mode are you using? (paper/testnet/live)
- What specific discrepancies are you seeing?
- Are balances off, or trade records, or PnL calculations?
- Have you made any manual trades on Polymarket outside of PolyEdge?
