# Fee Calculation Methodology

## Overview

This document explains how trading fees are captured, tracked, and analyzed in the Polyedge trading bot.

## Polymarket Fee Structure

Polymarket charges a **2% fee** on all trades:
- **Maker fee**: 2% (0.02)
- **Taker fee**: 2% (0.02)

These fees are applied to the notional value of the trade and are **implicit in the fill prices** returned by the CLOB API.

## How Fees Are Captured

### 1. Fee Capture at Order Execution

When an order is executed via the Polymarket CLOB API, the fill price already includes the fee. The fee is captured in two ways:

**Method 1: Explicit Fee Field (Recommended)**
```python
# From CLOB API response
result = clob_client.create_order(...)
fee = result.fee  # Extracted from API response
trade.fee = fee   # Stored in database
```

**Method 2: Implicit in Fill Price**
```python
# Fee is already included in the fill price
fill_price = result.price  # This price already has fees deducted
# No separate fee calculation needed
```

### 2. Fee Storage

Fees are stored in the `Trade` model:
```python
class Trade(Base):
    fee = Column(Float, nullable=True)  # Fee amount in USD
    slippage = Column(Float, nullable=True)  # Slippage in USD
```

## Slippage Calculation

Slippage is the difference between the expected price and the actual fill price. It's calculated as:

```
slippage = fill_price - entry_price
```

**Example:**
- Entry price (expected): $0.65
- Fill price (actual): $0.64
- Slippage: -$0.01 (negative = worse than expected)

Slippage is tracked separately from fees to help analyze execution quality.

## P&L Calculation

The P&L calculation **does NOT double-count fees**:

```
P&L = (settlement_value - entry_price) * size
```

The entry_price already includes fees, so the P&L reflects the true realized gain/loss.

**Example:**
- Entry price (with fees): $0.65
- Settlement value: $1.00 (UP position wins)
- Size: 100 shares
- P&L = (1.00 - 0.65) * 100 = $35.00

## Fee Analysis

### Querying Trades by Fee

```python
from backend.models.database import SessionLocal, Trade

db = SessionLocal()

# Find all trades with fees
trades_with_fees = db.query(Trade).filter(Trade.fee.isnot(None)).all()

# Calculate total fees paid
total_fees = db.query(func.sum(Trade.fee)).scalar()

# Find high-fee trades (>$1)
high_fee_trades = db.query(Trade).filter(Trade.fee > 1.0).all()
```

### Querying Trades by Slippage

```python
# Find trades with negative slippage (worse than expected)
bad_slippage = db.query(Trade).filter(Trade.slippage < 0).all()

# Find trades with slippage > 1%
high_slippage = db.query(Trade).filter(
    Trade.slippage > (Trade.entry_price * 0.01)
).all()
```

## Fee Impact on Returns

### Example Calculation

**Scenario**: Buy 100 shares at $0.65 with 2% fee

1. **Entry Cost**:
   - Notional: 100 * $0.65 = $65.00
   - Fee (2%): $65.00 * 0.02 = $1.30
   - Total cost: $66.30

2. **Exit (UP wins)**:
   - Settlement value: $1.00
   - Gross proceeds: 100 * $1.00 = $100.00
   - Fee (2%): $100.00 * 0.02 = $2.00
   - Net proceeds: $98.00

3. **Net P&L**:
   - Gross P&L: $100.00 - $65.00 = $35.00
   - Total fees: $1.30 + $2.00 = $3.30
   - Net P&L: $35.00 - $3.30 = $31.70

## Monitoring Fees

### Alert Thresholds

The monitoring system tracks high-fee trades:
- **Warning**: Fees > 2% of position value
- **Critical**: Fees > 5% of position value

### Fee Metrics

Key metrics to monitor:
- **Average fee per trade**: Total fees / number of trades
- **Fee as % of P&L**: Total fees / total P&L
- **Fee impact on win rate**: Trades that would win without fees but lose with fees

## Implementation Details

### Fee Capture in Strategy Executor

```python
# backend/core/strategy_executor.py
result = await clob_client.create_order(...)
trade.fee = result.fee  # Capture fee from API response
trade.slippage = result.price - decision['entry_price']  # Calculate slippage
db.add(trade)
db.commit()
```

### Fee Tracking in Settlement

```python
# backend/core/settlement.py
# Fees are already included in entry_price
# No additional fee deduction needed in settlement
pnl = (settlement_value - entry_price) * size
```

## References

- [Polymarket Fee Structure](https://polymarket.com/docs/fees)
- [Trade Model](../backend/models/database.py)
- [Strategy Executor](../backend/core/strategy_executor.py)
- [Settlement Engine](../backend/core/settlement.py)
