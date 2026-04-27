# ADR-002: Live BotState Equity Source

**Status:** Accepted  
**Date:** 2026-04-27

## Context

`BotState` is a dashboard/risk cache, while `Trade` is the durable learning ledger. Live-mode ledger rows can include historical backfills and reconstructed positions, so local realized P&L is not a reliable source of current live account equity.

Polymarket Data API `/value` reports open-position value only. It excludes idle CLOB USDC cash, so using `/value` alone understates equity.

## Decision

Live `BotState.bankroll` is derived from external account equity:

```text
live_equity = CLOB USDC cash balance + Polymarket Data API /value open-position value
live_total_pnl = live_equity - INITIAL_BANKROLL
```

Only `backend.core.bankroll_reconciliation.reconcile_bot_state()` may update live `bankroll`/`total_pnl`. Runtime settlement and wallet-sync code must preserve trade history and call reconciliation instead of writing live financial fields directly.

## Consequences

- Historical trades remain intact for re-learning and attribution.
- Live bankroll cannot be inferred from local realized P&L/backfill rows.
- Paper/testnet can remain ledger-derived because they are simulated/accounting modes, but available-bankroll fields are a non-negative balance invariant across settlement, reconciliation, and API/dashboard output; cumulative simulated PnL may stay negative to preserve the full loss history.
- Dashboard views must label live, paper, and testnet PnL separately so operators can see loss trades without mistaking them for current live account equity.
- Tests that need synthetic live `BotState` values must opt in with `Session.info["allow_live_financial_update"] = True` or use the reconciliation path.
