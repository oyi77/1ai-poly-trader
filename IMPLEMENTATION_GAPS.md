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

~~**Tests used stale Trade schema** — integration tests created `Trade` with `exit_price`, `exchange`, `strategy`, `order_id` columns not present.~~ → **Fixed** (2026-05-03): `backend/tests/test_autonomy_loop_integration.py` corrected: Trade creation uses actual columns (`settled`, `settlement_value`, `pnl`, `result`); tests marked `@pytest.mark.asyncio`; assertions aligned with actual return return dict keys; `BankrollAllocator` calls `run_once()` not `allocate_daily_capital()`.

~~**Timezone handling bugs in promoter** — naive datetime subtraction raised errors in `_check_shadow_criteria` and paper retirement age calculation.~~ → **Fixed** (2026-05-03): Added `.replace(tzinfo=timezone.utc)` guards before naive-aware subtraction.

~~**Registry import typo** — promoter imported `_registry` instead of `STRATEGY_REGISTRY`.~~ → **Fixed** (2026-05-03): `from backend.strategies.registry import STRATEGY_REGISTRY`.

~~**StrategyPerformanceRegistry missing** — No centralized `StrategyReport` store with per-strategy metrics updated after each settlement.~~ → **Fixed** (2026-05-03): `backend/core/strategy_performance_registry.py` implements `StrategyPerformanceRegistry` singleton with `StrategyReport` dataclass, DB persistence via `StrategyPerformanceSnapshot` ORM, wired into `settlement_helpers.py`. Tests in `backend/tests/test_strategy_performance_registry.py`.

~~**TransactionEvent model missing** — No ledger for deposits/withdrawals/settlements across paper/live/testnet modes.~~ → **Fixed** (2026-05-03): Added `TransactionEvent` model to `backend/models/database.py` with emission hooks in `settlement_helpers.py` (settlement events) and `bankroll_reconciliation.py` (reconciliation adjustments).

~~**Experiment FK missing** — `Experiment.strategy_name` had no foreign key to `StrategyConfig`.~~ → **Fixed** (2026-05-03): Added `ForeignKey("strategy_config.strategy_name", ondelete="CASCADE")`.

~~**Auto-enable strategy scheduling unverified** — `_enable_strategy()` may have fired `schedule_strategy()` before DB commit.~~ → **Fixed** (2026-05-03): Verified `db.commit()` happens BEFORE `schedule_strategy()` call; integration test asserts scheduling invocation.

~~**Risk Profile not implemented** — ADR-005 defined safe/normal/aggressive/extreme profiles but no code existed; `RISK_PROFILE` not in config.~~ → **Fixed** (2026-05-03): `backend/core/risk_profiles.py` implements four static profiles as preset overlays for runtime settings; `apply_profile()` mutates settings and persists to `.env`; API endpoints `GET/PUT /api/v1/settings/risk/profile`; tests in `backend/tests/test_risk_profiles.py`.

~~**Bankroll allocation not enforced** — `BankrollAllocator` computed per-strategy budgets but `RiskManager.validate_trade` didn't use them.~~ → **Fixed** (2026-05-03): Added `strategy_name` param to `validate_trade()`; new `_strategy_allocation_cap()` method fetches allocation from `BotState.misc_data` and caps trade size to remaining budget; `strategy_executor.py` passes `strategy_name`; tests in `backend/tests/test_allocation_enforcement.py`.

~~**TradeForensics missing timedelta import** — `analyze_recent_losses()` crashed with `NameError` on `timedelta` reference.~~ → **Fixed** (2026-05-03): Added `timedelta` to datetime import in `backend/core/trade_forensics.py:10`.

~~**Promoter operator precedence crash** — `(datetime.now() - exp.promoted_at or exp.created_at).days` evaluated as `(datetime.now() - None)` when `promoted_at` is null → `TypeError`.~~ → **Fixed** (2026-05-03): Added None guard with `ref_time` extraction in `autonomous_promoter.py` shadow/paper/live evaluation loops.

~~**ExperimentRecord missing strategy_name FK** — Promoter used `exp.name` (free-text) as strategy identifier for health checks and `_enable_strategy`, causing mismatches.~~ → **Fixed** (2026-05-03): Added `strategy_name = Column(String, ForeignKey(...))` to `ExperimentRecord` in `kg_models.py`; promoter uses `exp.strategy_name or exp.name`.

~~**StrategyOutcome table never populated** — `strategy_health.py:assess()` queries `StrategyOutcome` for kill/warn decisions, but no code path wrote rows to it.~~ → **Fixed** (2026-05-03): Added `StrategyOutcome` emission hook in `settlement_helpers.py` after each settlement (guarded by `if trade.strategy`).

~~**StrategyPerformanceRegistry PSI from empty table** — `compute_psi(strategy, session)` queried empty `StrategyOutcome` so PSI was always 0.0.~~ → **Fixed** (2026-05-03): Replaced with inline PSI computation from Trade data (recent 30 vs previous 30) in `strategy_performance_registry.py:261-289`.

~~**Settlement double-processing** — `process_settled_trade` had no idempotency guard; crash+restart could cause duplicate StrategyOutcome rows, double-counted PnL, duplicate broadcasts.~~ → **Fixed** (2026-05-03): Added early return if `trade.settled and trade.pnl is not None` in `settlement_helpers.py:957`.

~~**auto_disable_losing_strategies mixed trading modes** — Queried trades without `trading_mode` filter; paper losses could disable live strategies and vice versa.~~ → **Fixed** (2026-05-03): Added `Trade.trading_mode == current_mode` filter in `scheduler.py:auto_disable_losing_strategies`.

~~**AGI_STRATEGY_HEALTH_ENABLED never enforced** — Config flag existed but no production code checked it; health monitoring always ran.~~ → **Fixed** (2026-05-03): Promoter now checks `getattr(settings, "AGI_STRATEGY_HEALTH_ENABLED", True)` before creating `StrategyHealthMonitor`; returns benign defaults when disabled.

~~**auto_allocate doesn't redistribute capped excess** — When a strategy hit the 50% cap, the excess was lost rather than redistributed to other strategies.~~ → **Fixed** (2026-05-03): `strategy_ranker.py:auto_allocate` now redistributes excess from capped strategies proportionally to uncapped ones in a second pass.

~~**Bankroll allocator didn't filter BotState by mode** — Queried `BotState.first()` without mode filter, potentially using wrong mode's bankroll for allocation.~~ → **Fixed** (2026-05-03): `bankroll_allocator.py` now queries `BotState.filter_by(mode=settings.TRADING_MODE).first()` with fallback to `.first()`.

~~**Rejection learner treated JSON string as dict** — `cfg.params` is a Text/JSON column stored as string; rejection_learner accessed `.get()` directly on it, which would raise `AttributeError` at runtime.~~ → **Fixed** (2026-05-03): Added `json.loads()` parsing in `rejection_learner.py:157` with fallback to empty dict.

~~**StrategyRanker.disable_underperformers didn't pass trading_mode** — Same pattern as auto_disable_losing_strategies; could disable strategies based on wrong mode's data.~~ → **Fixed** (2026-05-03): Added `trading_mode` parameter to `disable_underperformers()`, passed from `strategy_ranking_job` via `settings.TRADING_MODE`.

~~**OnlineLearner bypassed AGI_STRATEGY_HEALTH_ENABLED flag** — `online_learner.py` called `_health_monitor.assess()` unconditionally on every settlement, killing strategies even when the feature flag was disabled.~~ → **Fixed** (2026-05-03): Added `_health_enabled()` helper that checks `settings.AGI_STRATEGY_HEALTH_ENABLED`; health assess calls in `on_trade_settled()` and `run_cycle()` now gated by this check.

~~**Duplicate StrategyOutcome rows per settlement** — Both `OnlineLearner.on_trade_settled()` → `record_outcome()` AND `settlement_helpers.py` direct emission created StrategyOutcome rows for the same trade, doubling health metrics.~~ → **Fixed** (2026-05-03): Removed direct StrategyOutcome emission from `settlement_helpers.py`; `record_outcome()` via `OnlineLearner` is the single source of truth for outcome recording.

~~**self_review.py treated StrategyConfig.params JSON string as dict** — `_generate_proposals_for_bleeders` called `.items()` on `cfg.params` without parsing JSON, causing AttributeError on proposal generation.~~ → **Fixed** (2026-05-03): Added `json.loads()` with fallback for string-typed params.

~~**GET /api/learning/health endpoints disabled strategies as side effect** — `StrategyHealthMonitor.assess()` both computes metrics AND disables killed strategies. GET endpoints triggered this on every dashboard health check.~~ → **Fixed** (2026-05-03): Added `readonly` parameter to `assess()`; API endpoints now pass `readonly=True` to compute metrics without side effects.

~~**trade_forensics.py loss streak query used wrong direction** — `Trade.timestamp >= trade.timestamp` counted future (non-existent) losses instead of preceding losses. Loss streak detection was non-functional.~~ → **Fixed** (2026-05-03): Changed to `<=` with 24-hour lookback window for correct streak detection.

~~**No HistoricalDataCollector** — No collector for BTC candles, weather history, market outcomes. Backtest used unit-test data only.~~ → **Fixed** (2026-05-03): Added `backend/core/historical_data_collector.py` with `HistoricalDataCollector` class that collects BTC candles from Binance, settled market outcomes from Gamma API, and weather snapshots from Open-Meteo. ORM models in `backend/models/historical_data.py` (`HistoricalCandle`, `MarketOutcome`, `WeatherSnapshot`). Scheduled as `historical_data_collection_job` every 6h.

~~**No Fronttest validation** — Parameter changes went to live without a paper-trial gate.~~ → **Fixed** (2026-05-03): Added `backend/core/fronttest_validator.py` with `FronttestValidator` class. Validates that executed proposals survive a 14-day paper-trial period with minimum 10 trades and ≥40% win rate before allowing live deployment. Config: `AGI_FRONTTEST_DAYS`, `AGI_FRONTTEST_MIN_TRADES`.

~~**No AGI health check** — No scheduled job validating strategy health, data freshness, budget exhaustion, orphaned positions, scheduler liveness.~~ → **Fixed** (2026-05-03): Added `backend/core/agi_health_check.py` with `AGIHealthChecker` running 5 checks: strategy staleness, data freshness (<24h), budget status, scheduler liveness, orphaned positions (>7d unsettled). Scheduled as `agi_health_check_job` every 15 minutes.

~~**No nightly review** — No daily markdown log writer; no base rate calibration or improvement plan.~~ → **Fixed** (2026-05-03): Added `backend/core/nightly_review.py` with `NightlyReviewWriter` generating `docs/agi-log/YYYY-MM-DD.md` containing daily summary, strategy performance (7-day), model calibration, and improvement plan with pending proposals + disabled strategies. Scheduled as `nightly_review_job` at configurable hour.

~~**No strategy rehabilitation** — No automated pipeline to re-enable suspended strategies after validation.~~ → **Fixed** (2026-05-03): Added `backend/core/strategy_rehabilitator.py` with `StrategyRehabilitator`. Re-enables disabled strategies after 7-day cooldown if recent trades show ≥50% win rate and positive PnL. Scheduled as `strategy_rehabilitation_job` daily.

~~**TradeForensics not integrated into AGI improvement** — Forensics ran on losses but didn't feed patterns back into proposals.~~ → **Fixed** (2026-05-03): Added `backend/core/forensics_integration.py` with `generate_forensics_proposals()`. Groups losses by strategy over 7 days, creates `StrategyProposal` entries for strategies with ≥5 losses. Scheduled as `forensics_integration_job` daily.

~~**.env.example missing RISK_PROFILE and AGI flags** — New config fields not documented.~~ → **Fixed** (2026-05-03): Added `RISK_PROFILE`, `AGI_HEALTH_CHECK_*`, `AGI_NIGHTLY_REVIEW_*`, `AGI_REHABILITATION_ENABLED`, `AGI_FRONTTEST_*`, `HISTORICAL_DATA_COLLECTOR_*` sections to `.env.example`.

~~**Hardcoded API base URLs across 30+ backend files** — Polymarket Gamma, Data, CLOB, Kalshi, Goldsky, Binance, Coinbase, Kraken, Bybit, CoinGecko, Open-Meteo, NWS URLs were hardcoded string constants.~~ → **Fixed** (2026-05-03): Added 20+ config fields to `backend/config.py` (`GAMMA_API_URL`, `DATA_API_URL`, `CLOB_API_URL`, `POLYMARKET_BASE_URL`, `KALSHI_API_URL`, `GOLDSKY_API_URL`, `BINANCE_API_URL`, `COINBASE_API_URL`, `KRAKEN_API_URL`, `BYBIT_API_URL`, `COINGECKO_API_URL`, `OPEN_METEO_API_URL`, `OPEN_METEO_ARCHIVE_URL`, `NWS_API_URL`, `NWS_BASE_URL`, `BINANCE_KLINES_URL`, `RESEARCH_RSS_FEEDS`). All 30+ files updated to read from settings. Commit `cf46a76`.

~~**Hardcoded frontend polling intervals** — 55 `refetchInterval` values across 35 .tsx files were hardcoded milliseconds.~~ → **Fixed** (2026-05-03): Created `frontend/src/polling.ts` with `POLL.FAST` (2s), `POLL.NORMAL` (10s), `POLL.SLOW` (30s), `POLL.VERY_SLOW` (60s) constants configurable via `VITE_POLL_*_MS` env vars. All 35 files updated. MiroFish hardcoded ports (5001/3200) now read from `VITE_MIROFISH_*` env vars. Commit `cf46a76`.

~~**Remaining hardcoded URLs in 17+ backend files** — First pass missed wallet_reconciliation, bankroll_reconciliation, auto_redeem, position_valuation, whale_discovery, WebSocket clients (5 files), weather geocoding/ensemble, web search providers, mirofish_client, CLOB book/midpoint URLs, historical_data_collector, heartbeat Telegram URL.~~ → **Fixed** (2026-05-03): Added 16 more config fields to `backend/config.py` (`POLYMARKET_RELAYER_URL`, `POLYMARKET_WS_CLOB_URL`, `POLYMARKET_WS_USER_URL`, `POLYMARKET_WS_RTDS_URL`, `POLYMARKET_WS_WHALE_URL`, `POLYMARKET_WS_ORDERBOOK_URL`, `QUICKNODE_RPC_URL`, `OPEN_METEO_ENSEMBLE_URL`, `OPEN_METEO_GEOCODING_URL`, `TELEGRAM_API_BASE`, `MIROFISH_API_URL`, `TAVILY_API_URL`, `EXA_API_URL`, `SERPER_API_URL`, `DDG_HTML_URL`, `POLYMARKET_WS_RTDS_URL`). All 22 files updated. Commit `78c1a3a`.

~~**Hardcoded trading parameter: MIN_ORDER_USDC = 5.0** — Critical business logic constant embedded in `polymarket_clob.py`.~~ → **Fixed** (2026-05-03): Added `MIN_ORDER_USDC` and `PAPER_MIN_ORDER_USDC` to config, converted `polymarket_clob.py` and `strategy_executor.py` to use `_cfg()` pattern. Commit `1c6dd32`.

~~**Hardcoded safe_param_tuner thresholds** — `MAX_CHANGE_PCT`, `MIN_TRADES_FOR_TUNING`, `REVERT_SIGMA_THRESHOLD` were constants.~~ → **Fixed** (2026-05-03): Added `SAFE_TUNER_MAX_CHANGE_PCT`, `SAFE_TUNER_MIN_TRADES_FOR_TUNING`, `SAFE_TUNER_REVERT_SIGMA_THRESHOLD` to config, converted `safe_param_tuner.py` to read from settings. Commit `1c6dd32`.

~~**Hardcoded HFT risk limits: POSITION_SIZE_PCT and MAX_POSITION_USD** — HFT risk manager had hardcoded position size percentage and max position cap.~~ → **Fixed** (2026-05-03): Added `HFT_POSITION_SIZE_PCT` and `HFT_MAX_POSITION_USD` to config, converted `risk_manager_hft.py` to use `_cfg()` pattern. Commit `1c6dd32`.

---

## Known Gaps

### Observability & Safety
- **Test isolation**: `tests/test_agi_autonomous_loop.py` patches global `SessionLocal` at import time, causing cross-contamination when run alongside `backend/tests/test_autonomy_loop_integration.py`. Pre-existing issue; tests pass individually.

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
