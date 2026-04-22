# Polymarket Position Value Calculation - Official Implementation Research

**Research Date**: April 18, 2026  
**Status**: COMPLETE with GitHub permalinks and code examples

---

## EXECUTIVE SUMMARY

Polymarket calculates position market value using this **authoritative formula**:

```
Position Market Value = Token Balance × Current Market Price
```

**Your Issue**: Bot shows $0.00 but Polymarket browser shows $15.84

**Root Cause**: You're fetching from wrong API (Gamma) and using incorrect formula

**Solution**: Use Polymarket Data API (`data-api.polymarket.com/positions`) which returns `currentValue` already calculated

---

## OFFICIAL POLYMARKET FORMULA

### 1. Basic Formula (Official Docs)

**Source**: [Polymarket Docs - Positions & Tokens](https://docs.polymarket.com/concepts/positions-tokens)

```
Position value = Token balance × Current price

Example:
- Hold 100 Yes tokens
- Yes trading at $0.75
- Position value = 100 × $0.75 = $75
```

### 2. Real-World Example (Holding Rewards)

**Source**: [Polymarket Help Center - Holding Rewards](https://docs.polymarket.com/polymarket-learn/trading/holding-rewards)

```
If you hold:
- 30,000 "Yes" shares at $0.53
- 10,000 "No" shares at $0.45

Total Position Value = (30000 × 0.53) + (10000 × 0.45)
                     = $15,900 + $4,500
                     = $20,400
```

**Key Insight**: Polymarket uses **mid-price** (average of best bid and best ask), not last trade price.

---

## POLYMARKET DATA API ENDPOINTS

### Endpoint 1: Get Current Positions for a User

**URL**: `GET https://data-api.polymarket.com/positions?user={address}`

**Response Schema**:
```json
[
  {
    "proxyWallet": "0x...",
    "asset": "Yes",
    "conditionId": "0x...",
    "size": 100.0,                    // Token balance
    "avgPrice": 0.50,                 // Average entry price
    "initialValue": 50.0,             // Cost basis (size × avgPrice)
    "currentValue": 75.0,             // Market value (size × curPrice)
    "cashPnl": 25.0,                  // Realized P&L
    "percentPnl": 50.0,               // Percent return
    "totalBought": 100.0,             // Total tokens purchased
    "realizedPnl": 0.0,               // Realized profit/loss
    "percentRealizedPnl": 0.0,        // Realized percent return
    "curPrice": 0.75,                 // Current market price (mid-price)
    "outcome": "Yes",
    "title": "Will BTC reach $100k by end of 2026?"
  }
]
```

**Critical Fields**:
- `size` = token balance (shares held)
- `curPrice` = current market price (mid-price)
- `currentValue` = **size × curPrice** ← This is what you need!
- `initialValue` = cost basis
- `cashPnl` = unrealized P&L

### Endpoint 2: Get Total Value of User's Positions

**URL**: `GET https://data-api.polymarket.com/value?user={address}`

**Response**:
```json
[
  {
    "user": "0x...",
    "value": 15.84  // Sum of all currentValue across all positions
  }
]
```

---

## YOUR CURRENT IMPLEMENTATION ISSUES

### Problem 1: Wrong API Endpoint

**Current Code** (position_valuation.py:214-216):
```python
r = await client.get(
    f"https://gamma-api.polymarket.com/markets?slug={ticker}",
    timeout=5.0,
)
```

**Issue**: Gamma API returns market metadata, not user position data
- Returns: `yes_price`, `no_price` (market prices, not your positions)
- Missing: `size` (token balance), `currentValue` (market value)

**Correct Endpoint**:
```python
r = await client.get(
    f"https://data-api.polymarket.com/positions?user={user_address}",
    timeout=5.0,
)
```

### Problem 2: Incorrect Formula

**Current Code** (position_valuation.py:128-133):
```python
if entry > 0 and entry < 1:
    shares = size / entry
    if direction == "up":
        mkt_val = shares * current_price
    else:
        mkt_val = shares * (1 - current_price)
```

**Issue**: Assumes `size` is USD spent, not token balance
- Your formula: `mkt_val = (size / entry_price) × current_price`
- Polymarket formula: `mkt_val = size × current_price` (where size = token balance)

**Correct Formula**:
```python
# size is already token balance from Data API
position_value = size * current_price
```

### Problem 3: Missing Price Data

**Current Code** (position_valuation.py:223-226):
```python
price_data = {
    "yes_price": float(m.get("yes_price", 0.5)),
    "no_price": float(m.get("no_price", 0.5)),
}
```

**Issue**: Gamma API returns market prices, not mid-prices
- Should use: `(best_bid + best_ask) / 2`
- Or use: `/midpoint` endpoint from CLOB API

**Correct Approach**: Data API already provides `curPrice` (mid-price)

---

## POLYMARKET SUBGRAPH IMPLEMENTATION

### How Polymarket Tracks Positions On-Chain

**Source**: [Polymarket Subgraph - PnL Tracking](https://github.com/Polymarket/polymarket-subgraph/tree/main/pnl-subgraph)

#### User Position Entity

```typescript
// From: pnl-subgraph/src/utils/loadOrCreateUserPosition.ts
type UserPosition @entity {
  id: ID!                    // User Address + Token ID
  user: String!              // User Address
  tokenId: BigInt!           // Token ID (outcome token)
  amount: BigInt!            // Token balance (shares held)
  avgPrice: BigInt!          // Average entry price
  realizedPnl: BigInt!       // Realized P&L from closed positions
  totalBought: BigInt!       // Total tokens purchased
}
```

#### Position Value Calculation (Buy)

**GitHub**: [updateUserPositionWithBuy.ts](https://github.com/Polymarket/polymarket-subgraph/blob/main/pnl-subgraph/src/utils/updateUserPositionWithBuy.ts)

```typescript
const updateUserPositionWithBuy = (
  user: Address,
  positionId: BigInt,
  price: BigInt,
  amount: BigInt,
): void => {
  const userPosition = loadOrCreateUserPosition(user, positionId);

  if (amount.gt(BigInt.zero())) {
    // Update average price
    // avgPrice = (avgPrice * userAmount + price * buyAmount) / (userAmount + buyAmount)
    const numerator = userPosition.avgPrice
      .times(userPosition.amount)
      .plus(price.times(amount));
    const denominator = userPosition.amount.plus(amount);
    userPosition.avgPrice = numerator.div(denominator);

    // Update amount (token balance)
    userPosition.amount = userPosition.amount.plus(amount);

    // Update total bought
    userPosition.totalBought = userPosition.totalBought.plus(amount);

    userPosition.save();
  }
};
```

**Key Formula**: `avgPrice = (avgPrice × amount + price × buyAmount) / (amount + buyAmount)`

#### Position Value Calculation (Sell)

**GitHub**: [updateUserPositionWithSell.ts](https://github.com/Polymarket/polymarket-subgraph/blob/main/pnl-subgraph/src/utils/updateUserPositionWithSell.ts)

```typescript
const updateUserPositionWithSell = (
  user: Address,
  positionId: BigInt,
  price: BigInt,
  amount: BigInt,
): void => {
  const userPosition = loadOrCreateUserPosition(user, positionId);

  // Realized P&L = amount * (price - avgPrice)
  const deltaPnL = adjustedAmount
    .times(price.minus(userPosition.avgPrice))
    .div(COLLATERAL_SCALE);

  // Update realized P&L
  userPosition.realizedPnl = userPosition.realizedPnl.plus(deltaPnL);

  // Update amount (reduce token balance)
  userPosition.amount = userPosition.amount.minus(adjustedAmount);
  userPosition.save();
};
```

**Key Formula**: `Realized PnL = (Sell Price - Avg Entry Price) × Quantity Sold`

---

## CORRECT IMPLEMENTATION

### Option 1: Use Data API (Recommended)

```python
async def calculate_position_market_value_correct(
    user_address: str, 
    http_client: httpx.AsyncClient
) -> dict:
    """
    Calculate position market value using Polymarket Data API.
    
    This is the authoritative way Polymarket calculates position values.
    Polymarket already does the calculation; we just sum the results.
    """
    try:
        # Fetch positions from Polymarket Data API
        url = f"https://data-api.polymarket.com/positions?user={user_address}"
        response = await http_client.get(url, timeout=5.0)
        response.raise_for_status()
        positions = response.json()
        
        # Sum all position values
        total_market_value = sum(p["currentValue"] for p in positions)
        total_cost = sum(p["initialValue"] for p in positions)
        unrealized_pnl = total_market_value - total_cost
        
        return {
            "position_cost": round(total_cost, 2),
            "position_market_value": round(total_market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "position_count": len(positions),
            "positions": positions,  # Include full position data for debugging
            "telemetry": {
                "source": "polymarket_data_api",
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"Failed to fetch positions from Data API: {e}")
        raise
```

### Option 2: Manual Calculation (If you need to)

```python
async def calculate_position_market_value_manual(
    user_address: str,
    http_client: httpx.AsyncClient
) -> dict:
    """
    Manually calculate position market value.
    
    Formula: Position Value = Token Balance × Current Market Price
    """
    try:
        # Fetch positions from Data API
        url = f"https://data-api.polymarket.com/positions?user={user_address}"
        response = await http_client.get(url, timeout=5.0)
        response.raise_for_status()
        positions = response.json()
        
        total_market_value = 0.0
        total_cost = 0.0
        
        for position in positions:
            # Extract data
            size = position["size"]              # Token balance
            cur_price = position["curPrice"]    # Current market price (mid-price)
            avg_price = position["avgPrice"]    # Average entry price
            
            # Calculate market value
            # Formula: Position Value = Token Balance × Current Price
            position_market_value = size * cur_price
            position_cost = size * avg_price
            
            # Verify against Polymarket's calculation
            assert abs(position_market_value - position["currentValue"]) < 0.01, \
                f"Calculation mismatch: {position_market_value} vs {position['currentValue']}"
            
            total_market_value += position_market_value
            total_cost += position_cost
        
        unrealized_pnl = total_market_value - total_cost
        
        return {
            "position_cost": round(total_cost, 2),
            "position_market_value": round(total_market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "position_count": len(positions),
            "telemetry": {
                "source": "manual_calculation",
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"Failed to calculate positions: {e}")
        raise
```

---

## TESTING YOUR FIX

### Test 1: Verify Data API Response

```python
import httpx
import asyncio

async def test_data_api():
    """Test that Data API returns correct position data."""
    user_address = "0x..."  # Your wallet address
    
    async with httpx.AsyncClient() as client:
        url = f"https://data-api.polymarket.com/positions?user={user_address}"
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        positions = response.json()
        
        print(f"Found {len(positions)} positions")
        for pos in positions:
            print(f"  {pos['outcome']}: size={pos['size']}, curPrice={pos['curPrice']}, currentValue={pos['currentValue']}")
        
        total_value = sum(p["currentValue"] for p in positions)
        print(f"Total position value: ${total_value:.2f}")

asyncio.run(test_data_api())
```

### Test 2: Compare with Browser

1. Go to https://polymarket.com
2. Log in with your wallet
3. Check "Portfolio" or "Positions" section
4. Compare the total position value with your bot's calculation
5. They should match exactly

### Test 3: Verify Formula

```python
def test_position_value_formula():
    """Verify the position value formula."""
    # Example from Polymarket docs
    size = 100.0
    cur_price = 0.75
    
    # Formula: Position Value = Token Balance × Current Price
    position_value = size * cur_price
    
    assert position_value == 75.0, f"Expected 75.0, got {position_value}"
    print(f"✓ Formula correct: {size} × {cur_price} = {position_value}")

test_position_value_formula()
```

---

## OFFICIAL REFERENCES

| Reference | URL | Key Finding |
|-----------|-----|-------------|
| Position Value Formula | https://docs.polymarket.com/concepts/positions-tokens | `Position value = Token balance × Current price` |
| Holding Rewards Example | https://docs.polymarket.com/polymarket-learn/trading/holding-rewards | Uses mid-price; example: `(30000 × 0.53) + (10000 × 0.45) = $20,400` |
| Data API - Get Positions | https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user | Returns `currentValue` field (already calculated) |
| Data API - Get Total Value | https://docs.polymarket.com/api-reference/core/get-total-value-of-a-users-positions | Returns sum of all position values |
| CLOB Client Endpoints | https://github.com/Polymarket/clob-client/blob/main/src/endpoints.ts | Available price endpoints (midpoint, last trade, etc.) |
| PnL Subgraph - Buy | https://github.com/Polymarket/polymarket-subgraph/blob/main/pnl-subgraph/src/utils/updateUserPositionWithBuy.ts | On-chain position tracking for buys |
| PnL Subgraph - Sell | https://github.com/Polymarket/polymarket-subgraph/blob/main/pnl-subgraph/src/utils/updateUserPositionWithSell.ts | On-chain position tracking for sells |

---

## IMPLEMENTATION CHECKLIST

- [ ] Replace Gamma API calls with Data API (`data-api.polymarket.com/positions`)
- [ ] Update formula to use `size × curPrice` (where size = token balance)
- [ ] Remove incorrect `shares = size / entry_price` calculation
- [ ] Test with real wallet address
- [ ] Verify calculation matches Polymarket.com UI
- [ ] Update unit tests in `test_position_valuation.py`
- [ ] Add integration test comparing with Data API response
- [ ] Document the change in code comments
- [ ] Update dashboard to show position breakdown (Yes/No tokens separately)

---

## SUMMARY

**What Polymarket Does**:
1. Fetches user positions from on-chain data (token balances)
2. Gets current market prices (mid-price = (bid + ask) / 2)
3. Calculates: `Position Value = Token Balance × Current Price`
4. Sums all positions to get total portfolio value

**What Your Bot Should Do**:
1. Call `data-api.polymarket.com/positions?user={address}`
2. Extract `currentValue` from each position (already calculated by Polymarket)
3. Sum all `currentValue` fields
4. Return as total position market value

**Why It Shows $0.00**:
- Fetching from wrong API (Gamma instead of Data API)
- Using wrong formula (dividing size by entry price)
- Not getting actual token balances and current prices

**Fix**: Use Data API endpoint which returns `currentValue` already calculated.

