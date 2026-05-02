# Implementation Gaps — PolyEdge Trading Bot

**Last Updated:** 2026-05-03

This file is the single source of truth for what's built vs planned. Every future agent must
read this before proposing work — avoid re-litigating already-completed items.

Format: 
- **Fixed** (YYYY-MM-DD): one-line of what was built and which files changed.
- **Known Gaps**: items not yet implemented.
- **Intentionally De-Scoped**: items we consciously chose not to do (with reason).

---

## Fixed

~~**No autonomous experiment lifecycle** — strategies existed as code but had no automated promotion/demotion pipeline; paper→live required manual intervention every time; no retirement mechanism for losing strategies.~~ → **Fixed** (2026-05-03): Added full autonomy loop: `backend/core/autonomous_promoter.py` implements DRAFT→SHADOW→PAPER→LIVE_PROMOTED→RETIRED lifecycle with promotion thresholds and health-based kill checks; `backend/core/bankroll_allocator.py` computes daily capital allocation via `StrategyRanker.auto_allocate()` and persists to `BotState.misc_data`; `backend/core/trade_forensics.py` analyzes losing trades for root causes; `backend/core/strategy_health.py` (`StrategyHealthMonitor.assess`) computes win rate, Sharpe, drawdown, Brier, PSI and auto-disables killed strategies. Wired into `backend/core/scheduler.py` as `autonomous_promotion_job` (every 6h) and `bankroll_allocation_job` (daily). Integration tests in `backend/tests/test_autonomy_loop_integration.py` validate complete pipeline.

~~**Promoter missing LIVE_PROMOTED evaluation** — after promotion to live, experiments were never checked for kill/retirement, causing live strategies to run forever even if health deteriorated.~~ → **Fixed** (2026-05-03): Added LIVE evaluation block in `autonomous_promoter.py:215-230`. `StrategyHealthMonitor.assess()` now runs on `LIVE_PROMOTED` experiments; `status="killed"` → `RETIRED`.

~~**TradeForensics referenced non-existent column** — `analyze_losing_trade()` used `trade.exit_price` which doesn't exist in Trade schema (uses `settlement_value`).~~ → **Fixed** (2026-05-03): `backend/core/trade_forensics.py:61-74` replaced `exit_price` with `settlement_value` context; used safe `getattr(trade, "strategy", None)` for optional fields.

~~**Tests used stale Trade schema** — integration tests created `Trade` with `exit_price`, `exchange`, `strategy`, `order_id` columns not present.~~ → **Fixed** (2026-05-03): `backend/tests/test_autonomy_loop_integration.py` corrected: Trade creation uses actual columns (`settled`, `settlement_value`, `pnl`, `result`); tests marked `@pytest.mark.asyncio`; assertions aligned with actual return dict keys; `BankrollAllocator` calls `run_once()` not `allocate_daily_capital()`.

~~**Timezone handling bugs in promoter** — naive datetime subtraction raised errors in `_check_shadow_criteria` and paper retirement age calculation.~~ → **Fixed** (2026-05-03): Added `.replace(tzinfo=timezone.utc)` guards before naive-aware subtraction.

~~**Registry import typo** — promoter imported `_registry` instead of `STRATEGY_REGISTRY`.~~ → **Fixed** (2026-05-03): `from backend.strategies.registry import STRATEGY_REGISTRY`.

---

## Known Gaps

### AGI Framework — Phase 1 (Foundation)
- **StrategyPerformanceRegistry**: No centralized `StrategyReport` store with per-strategy metrics updated after each settlement. Needed for dashboard visibility and promotion decisions.
- **TransactionEvent model**: No ledger for deposits/withdrawals/settlements across paper/live/testnet modes. External cash movements invisible.
- **Risk Profile UI with real effect**: `RiskManager` does not yet read from configurable risk profiles (conservative/moderate/aggressive). Profiles defined in ADR-005 but not wired.
- **Auto-enable strategy scheduling**: `_enable_strategy()` calls `schedule_strategy()` but may fire before DB commit; needs integration test verification.

### AGI Framework — Phase 2 (Data & Backtest)
- **HistoricalDataCollector**: No collector for BTC candles (Coinbase/Kraken/Binance), weather history (Open-Meteo archive), Polymarket outcomes, Kalshi outcomes. Backtest currently unit‑test data only.
- **BacktestEngine**: No replay engine that runs strategies against historical data with slippage/fees and returns `StrategyReport`.
- **Fronttest validation**: No 14-day paper‑trial gate for parameter changes before going live.
- **Proposal pipeline**: No `Proposal` model/API; AGI doesn't generate or validate improvement proposals yet.

### AGI Framework — Phase 3 (Loop & Review)
- **AGI health check (every 15 min)**: No scheduled job that validates strategy health, data pipeline freshness, scheduler liveness, budget exhaustion, orphaned positions.
- **Nightly review**: No `docs/agi-log/YYYY-MM-DD.md` writer; no base rate calibration or improvement plan.
- **Strategy rehabilitation**: No automated pipeline to repair suspended strategies and re‑enter paper after validation.

### Observability & Safety
- **Bankroll allocation enforcement**: Allocations computed but not yet enforced in `RiskManager.validate_trade` (position size caps by strategy).
- **TradeForensics scope**: Only runs on settlement losses; not yet integrated into AGI improvement suggestions.
- **Experiment name ↔ strategy name identity**: Tests assume equality; production experiments may diverge. Need explicit `strategy_name` FK on `ExperimentRecord`.

### Documentation
- `docs/configuration.md` missing AGI autonomy flags documentation.
- `docs/how-it-works.md` missing autonomy lifecycle explanation.
- `docs/api.md` missing any new AGI endpoints (none yet, but placeholder needed).
- `ARCHITECTURE.md` missing autonomy daemon section and updated AGI module table.
- `backend/AGENTS.md` missing notes on autonomy modules and config flags.
- `.env.example` missing AGI flag section.

---

## Intentionally De-Scoped

- **Zero-balance paper mode**: Paper bankroll cannot go below $0.00; enforced at `BotState` setter. We preserve learning history even when depleted. This is intentional — see ADR-004.
- **Full AGI autonomous strategy composition**: Strategy synthesizer exists but generates code for review first. Live autonomous code deployment requires `AGI_AUTO_PROMOTE=true` explicit opt-in.
- **External transaction detection**: We defer blockchain event parsing to a future phase; current system only detects via balance delta in `bankroll_reconciliation`.

---

## How to Use This File

- **Adding a new gap**: Create a new entry under "Known Gaps" with a clear title and one-sentence description.
- **Marking fixed**: Copy the gap title, strikethrough it, add "→ **Fixed** (YYYY-MM-DD)" and a one-line summary of what was built. Keep the original description (don't delete). Commit with reference to issue/PR.
- **De-scoping**: Add under "Intentionally De-Scoped" with a brief reason (cost, complexity, out-of-scope for current milestone).

**Never remove a gap entirely.** History matters: seeing what was broken and how it was fixed is more valuable than a clean list.
