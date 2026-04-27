# ADR-004: Bounded Autonomous Sizing

**Status:** Accepted  
**Date:** 2026-04-28

## Context

PolyEdge is intended to be autonomously managed by AI and strategy logic, but trading autonomy must not mean unconstrained capital authority. Operators also need to understand why a profitable live headline can coexist with paper/testnet losses and why a strategy-requested size may be reduced or rejected.

The system already has deterministic controls in `RiskManager` for confidence thresholds, daily loss, drawdown, duplicate open positions, bankroll sizing, exposure caps, and slippage. The `TradeAttempt` ledger records requested size, adjusted size, risk reasons, and execution outcomes.

## Decision

Use **bounded autonomous sizing**:

1. Strategy/AI logic proposes a dynamic `suggested_size` from signal evidence such as edge and confidence.
2. Each strategy keeps an explicit mandate cap such as `max_position_usd`.
3. `RiskManager.validate_trade()` remains the non-bypassable authority that can clip size or reject the attempt.
4. `strategy_executor` applies venue/mode minimum order-size checks after risk adjustment.
5. `TradeAttempt` records the full path from requested size to adjusted size to final status.

BTC Oracle follows this pattern by scaling its requested size with edge and confidence while capping at `max_position_usd`. It does not modify drawdown, exposure, loss, or minimum-order controls.

## Alternatives Considered

1. **Fixed size only.** Rejected because it does not meet the product goal of autonomous AI-managed capital allocation and can over-size weak signals or under-size strong ones.
2. **Unconstrained AI sizing.** Rejected because it would let model output bypass risk mandates, drawdown breakers, and operator safety expectations.
3. **Risk-manager-only sizing.** Rejected because the risk manager should enforce mandates, not infer strategy conviction.
4. **Manual approval for every size.** Rejected for paper/autonomous learning because it blocks the intended autonomous loop; still appropriate for future high-risk live escalation tiers.

## Consequences

- AI/strategy autonomy improves because size now varies with signal strength.
- Safety remains deterministic: drawdown breakers, max exposure, bankroll caps, duplicate-position checks, and min-order gates still win over AI preference.
- Operators can audit sizing decisions through Control Room rather than guessing from logs.
- A future enhancement can add graduated drawdown sizing tiers or hash-chained immutable audit events without changing the core authority boundary.
