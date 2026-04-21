# WebSocket Real-Time Data Flow Analysis

## Issue Summary
The dashboard appears static despite an active WebSocket connection. Status badges (Idle/Live, Paper/Testnet/Live) and overview data don't update in real-time.

## Root Cause Analysis

### 1. **WebSocket Connection is Working**
- Backend: `stats_broadcaster()` task runs every 1 second (line 376 in main.py)
- Backend broadcasts to all connected clients via `stats_ws.broadcast()`
- Frontend: `useStats()` hook connects to `/ws/dashboard-data` and receives messages
- Connection status shows "Connected" in the footer

### 2. **Backend Sends Correct Data Structure**
The backend sends:
```json
{
  "type": "stats_update",
  "timestamp": "2026-04-20T19:57:30.879Z",
  "data": {
    "paper": { "pnl": 0, "bankroll": 10000, "trades": 0, "wins": 0, "win_rate": 0, ... },
    "testnet": { "pnl": 0, "bankroll": 100, "trades": 0, "wins": 0, "win_rate": 0, ... },
    "live": { "pnl": 0, "bankroll": 0, "trades": 0, "wins": 0, "win_rate": 0, ... }
  }
}
```

### 3. **Frontend Parsing Issue (CRITICAL BUG)**

**Location**: `/frontend/src/hooks/useStats.ts` lines 26-39

```typescript
ws.onmessage = (event) => {
  try {
    const msg = JSON.parse(event.data)
    if (msg.type === 'stats_update' && msg.data) {
      const isAllModesFormat = msg.data.paper && msg.data.testnet && msg.data.live
      
      if (isAllModesFormat) {
        setWsStats({
          ...wsStats,  // ❌ BUG: wsStats is null on first message!
          paper: msg.data.paper,
          testnet: msg.data.testnet,
          live: msg.data.live,
        } as BotStats)
      } else {
        setWsStats(msg.data)
      }
    }
  } catch (e) {
    console.error('Failed to parse stats WebSocket message:', e)
  }
}
```

**The Problem**:
- `wsStats` is initialized as `null` (line 6)
- When the first message arrives, `isAllModesFormat` is `true`
- The code does `{ ...wsStats, paper: ..., testnet: ..., live: ... }`
- Since `wsStats` is `null`, spreading it results in an incomplete object
- The object is missing critical fields like `is_running`, `mode`, `bankroll`, `total_trades`, etc.

### 4. **Why Status Badges Appear Static**

**Location**: `/frontend/src/pages/Dashboard.tsx` lines 158-170

```typescript
<span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase border ${
  unifiedStats.isRunning ? 'bg-green-500/10 text-green-500 border-green-500/20' 
  : 'bg-neutral-800 text-neutral-500 border-neutral-700'
}`}>
  {unifiedStats.isRunning ? 'Live' : 'Idle'}
</span>
```

The badge reads `unifiedStats.isRunning` from the `useStats()` hook. Since the WebSocket data is incomplete (missing `is_running`), it falls back to the default value `false`, showing "Idle" even when the bot is running.

### 5. **Why Overview Data Appears Static**

**Location**: `/frontend/src/components/dashboard/OverviewTab.tsx` lines 31-53

The component uses `useStats()` which returns incomplete data from the WebSocket. The stats object is missing:
- `is_running` → Always shows "Idle"
- `mode` → Always shows "Paper" 
- Top-level fields like `bankroll`, `total_trades`, `total_pnl` → Use fallback defaults

## The Fix

### Option 1: Merge Backend Data Structure (Recommended)
The backend should send the complete `BotStats` object, not just the mode-specific data:

**File**: `/backend/api/main.py` line 357-368

Change from:
```python
stats = await get_stats(db, None, mode=None)
await stats_ws.broadcast({
    "type": "stats_update",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "data": {
        "paper": stats.paper,
        "testnet": stats.testnet,
        "live": stats.live,
    },
})
```

To:
```python
stats = await get_stats(db, None, mode=None)
await stats_ws.broadcast({
    "type": "stats_update",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "data": stats.model_dump(),  # Send complete BotStats object
})
```

### Option 2: Fix Frontend Parsing (Alternative)
**File**: `/frontend/src/hooks/useStats.ts` line 26-39

Change from:
```typescript
if (isAllModesFormat) {
  setWsStats({
    ...wsStats,  // ❌ Bug: wsStats is null
    paper: msg.data.paper,
    testnet: msg.data.testnet,
    live: msg.data.live,
  } as BotStats)
}
```

To:
```typescript
if (isAllModesFormat) {
  // Construct a complete BotStats object with defaults
  const currentMode = msg.data.paper?.mode || 'paper'
  const activeStats = msg.data[currentMode] || msg.data.paper
  
  setWsStats({
    is_running: true,  // Assume running if receiving updates
    mode: currentMode,
    bankroll: activeStats.bankroll || 10000,
    total_trades: activeStats.trades || 0,
    winning_trades: activeStats.wins || 0,
    win_rate: activeStats.win_rate || 0,
    total_pnl: activeStats.pnl || 0,
    initial_bankroll: 10000,
    last_run: null,
    paper: msg.data.paper,
    testnet: msg.data.testnet,
    live: msg.data.live,
  } as BotStats)
}
```

## Recommendation

**Use Option 1** (backend fix) because:
1. The backend already has the complete `BotStats` object
2. Simpler and more maintainable
3. Frontend doesn't need to reconstruct missing fields
4. Consistent with REST API response structure
5. One-line change vs complex frontend logic

## Testing Checklist

After applying the fix:
- [ ] Status badge shows "Live" when bot is running
- [ ] Mode badge shows correct mode (Paper/Testnet/Live)
- [ ] Overview stats update in real-time (PnL, win rate, ROI)
- [ ] Active trades count updates
- [ ] WebSocket connection remains stable
- [ ] Fallback to REST API works when WebSocket disconnects
