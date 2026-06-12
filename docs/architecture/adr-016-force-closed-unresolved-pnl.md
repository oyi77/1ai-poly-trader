# ADR-016: `force_closed_unresolved` Trades Must Record a Real Loss PnL, Not 0.0

**Status:** Accepted
**Date:** 2026-06-13

## Context

`backend/core/scheduling/scheduler.py::_cleanup_stale_trades_job` force-settles
paper trades whose markets never resolved via Gamma after 5 days
(`stuck_paper`: `settled=True, pnl IS NULL, timestamp < now() - 5d`). Since
commit `e0bd9e1aa` ("force-settle paper trades >5d old with PnL=0
(neutral)", 2026-06-03), this block has set:

```python
t.pnl = 0.0
t.result = "loss"
t.settlement_value = 0.0
t.settlement_source = "force_closed_unresolved"
```

`result="loss"` and `pnl=0.0` are contradictory: a trade recorded as a loss
for win-rate purposes contributes *nothing* to PnL totals, hiding the actual
cost of the position. In production this has produced:

- **`unified_arb` (paper, DISABLED)**: all 2,830 settled trades have
  `result='loss'`, `settlement_source='force_closed_unresolved'`,
  `pnl=0.0`. Total cost basis of these positions (`entry_price * size`,
  direction=YES, avg entry ≈ $0.495, size=10 shares) is **$14,009.18** —
  this entire amount is a real, unrecorded paper loss that any aggregate
  "total paper PnL" metric currently omits.
- **`bond_scanner` (paper, ACTIVE, reported +$18,711 PnL / 39.6% WR per
  `backend/strategies/AGENTS.md`)**: 66 of its settled trades hit this same
  path with `pnl=0.0`, representing ~$42.30 of unrecorded loss. Smaller in
  absolute terms but the same bug applies to the strategy whose
  profitability is actively being tracked toward the
  "profitable both live & paper" goal.
- Several other strategies (`arb_scanner`, `cross_platform_arb`,
  `cex_pm_leadlag`, `crypto_oracle`, `weather_emos`, `line_movement_detector`,
  `longshot_bias`) have older `force_closed_unresolved` rows from a one-time
  backfill on 2026-06-06 that *did* compute a real (non-zero) pnl — so this
  bug is specific to trades settled by the **live** `_cleanup_stale_trades_job`
  since it started running with the `pnl=0.0` hardcode.

Net effect: any strategy whose paper positions land in markets Gamma can
never resolve (malformed/foreign tickers, "KX..." Kalshi-style slugs that
aren't real Polymarket markets, etc.) accumulates real losses that are
**invisible in PnL** while still being counted as losses in win-rate —
directly undermining "profitable both live & paper, not only theoretically"
by making aggregate PnL look better than reality.

## Decision

When force-closing a `stuck_paper` trade as `result="loss"`, compute `pnl`
via the existing `calculate_pnl()` helper using a `settlement_value` chosen
so the position is treated as a **total loss of its cost basis** —
consistent with `result="loss"` — rather than hardcoding `pnl=0.0`.

Added `total_loss_settlement_value(direction)` to
`backend/core/settlement/settlement_helpers.py`:　`yes`/`up`/`buy` positions
are worthless at `settlement_value=0.0`; `no`/`down`/`sell` positions are
worthless at `settlement_value=1.0`. This is the settlement_value that makes
`calculate_pnl()` return `-cost_basis` (a real loss) for either side of a
bet, instead of accidentally computing a win payout for NO/DOWN positions
(which `settlement_value=0.0` would do, since `0.0` means "the NO/DOWN
outcome occurred" — a win for a NO/DOWN holder).

No other settlement path is changed: `closed_unresolved` (position
reconciliation, `settlement.py:367-372`) and `stale_live_force_close`
(`scheduler.py:884-893`) already call `calculate_pnl(trade, 0.0)`
unconditionally — those are **not** touched by this ADR. (The latter may
have the same direction-blind issue for `no`/`down`/`sell` live trades, but
live trading is currently disabled per `backend/strategies/AGENTS.md`, so it
is out of scope here and not addressed by this change.)

## Alternatives Considered

1. **Keep `pnl=0.0`, change `result` to something other than `"loss"`** (e.g.
   `"unresolved"`, excluded from win-rate). Rejected — would retroactively
   improve win rates for every affected strategy (66 trades for
   `bond_scanner` alone), the opposite direction from "make numbers
   accurate, not better-looking." It also doesn't fix the underlying PnL
   blind spot — the cost basis genuinely left the bankroll in paper
   accounting and should show up somewhere.
2. **Mark-to-last-known-price instead of total loss.** Rejected — these
   trades have no `settlement_value` and Gamma has already failed to
   resolve them after 5 days; a "last known price" isn't a settlement and
   would require fetching live order books for dead/malformed tickers,
   adding complexity for markets that are likely never coming back.
3. **Backfill all historical `force_closed_unresolved, pnl=0.0` rows in the
   same migration.** Deferred to a follow-up data script — this ADR covers
   the forward-going code fix only. The `unified_arb` $14k figure and
   `bond_scanner` $42 figure above describe the *current* historical gap;
   correcting them retroactively is a data backfill, not a settlement-logic
   change, and should be reviewed separately given the "Trade records are
   append-only" guidance in `CLAUDE.md`.

## Consequences

- New `force_closed_unresolved` settlements (going forward) record
  `pnl = -cost_basis` (negative), consistent with `result="loss"`.
- Aggregate paper PnL for any strategy that newly hits this path will
  decrease (become more negative / less positive) by the cost basis of each
  force-closed position — this is **more accurate**, not a behavior
  regression.
- `unified_arb`'s existing 2,830 rows and `bond_scanner`'s 66 rows remain at
  `pnl=0.0` until a separate backfill script is run (see Alternative 3).
  Until then, "total paper PnL" dashboards still omit ~$14,051 of real
  losses across these two strategies from historical data, but the gap will
  not grow further for newly force-closed trades.
- `unified_arb` is already DISABLED per strategy governance; this ADR does
  not re-enable or otherwise change its execution status — it only makes its
  historical record-keeping (going forward) accurate.
