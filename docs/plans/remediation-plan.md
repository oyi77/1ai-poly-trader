# PolyEdge Remediation Plan — Full-Codebase Green

> Status: DRAFT FOR REVIEW · Scope: everything found broken in the 2026-08-26 audit
> Execution protocol (applies to every todo): branch `qa-remediation`, conventional commits
> per todo, literal receipt pasted before a todo is marked done, no scope creep beyond
> the item text. Rollback = `git revert <sha>` per commit; phases are independent.

## Success definition (whole-plan gate)
1. `python -m pytest backend/tests -q` → **0 failed**
2. `cd frontend && npm run build` → exit 0 (tsc+vite+docs)
3. `npm run test -- --run` → existing vitest suite stays green
4. Playwright console-error sweep over dashboard incl. new Meteora tab → 0 page errors
5. `.env.example` contains zero keys without a settings consumer; zero invalid placeholder values

---

## Phase B0 — PRODUCTION BUGS (do first, they affect live behavior)

### B0.1 Fix NameError crash in autonomous promoter health path
- Files: `backend/core/autonomous_promoter/workflow.py`
- Change: line 16 import extended to `from backend.core.strategy_health import disable_for_rehab, StrategyHealthMonitor`
- Why: line 44 instantiates StrategyHealthMonitor; module only imported disable_for_rehab ⇒ NameError whenever AGI_STRATEGY_HEALTH_ENABLED defaults True (confirmed traceback by scout).
- Acceptance: `pytest backend/tests/test_autonomy_loop_integration.py -q` → 1 passed; plus `python -c "from backend.core.autonomous_promoter.workflow import StrategyHealthMonitor"` exits 0.

### B0.2 Restore lost trade-created audit event
- Files: `backend/core/strategy_executor/paper_kalshi.py` (near Trade commit)
- Change: re-add `log_trade_created(db, trade.id, {...}, user_id=f"strategy:{strategy_name}")` deleted in commit 4bb8b9f6 during the package split (grep shows ZERO remaining prod callers ⇒ audit trail silently off).
- Acceptance: `pytest backend/tests/test_audit_integration.py::test_trade_creation_logs_audit_event -q` → passed; grep confirms ≥1 prod caller of log_trade_created.

## Phase A — Frontend production build repair (24 tsc errors → 0)

### A1 Restore AGI API surface in `src/api/agi.ts`
- Change: re-add the 6 missing type exports (`RegimeStatus, GoalStatus, DecisionEntry, ComposedStrategy, ExperimentResult, AGIStatus`) and the `agiAPI` object. Decision rule: shapes MUST mirror live backend responses — capture via `curl :8100/api/v1/agi/*` (router exists at main.py:179) and write interfaces from actual payloads; if a type now lives elsewhere in client.ts, re-export instead of duplicating.
- Fixes errors: agi.ts(1)x6 + the four components' TS2305 `agiAPI` errors.
- Acceptance: `npx tsc --noEmit 2>&1 | grep -c "src/api/agi"` → 0; component TS2305 count → 0.

### A2 Type-narrow AGIControlTab unknowns
- Change: replace implicit-any data flows with explicit response interfaces from A1 (`AGIStatus`, strategies array, totals); 10 sites at lines 33-34,120-121,129.
- Acceptance: tsc error count for AGIControlTab.tsx → 0.

### A3 Type AGIRegimeTab map params
- Change: annotate `(entry: RegimeEntry, idx: number)` at line 123 using an exported interface.
- Acceptance: TS7006 errors → 0.

### A4 Remove dead imports
- Change: drop unused `api` in src/api/bot.ts(1) and unused import decl in src/api/client.ts(1).
- Acceptance: TS6133/TS6192 → 0.

### A5 Full build gate
- Acceptance: `npm run build` exit 0 AND `npm run test -- --run` green (143 existing cases must not regress). Rollback note: all changes confined to src/api+admin components; revert commit restores prior state.

---

## Phase B — Backend suite to zero (31 → 0)

### B1 Stale-import sweep (3 files, S)
- timeout_handling: import execute_with_timeout from backend.models.recovery
- risk_profiles: repoint logger patches to backend.core.risk.risk_profiles.logger.* (verified path)
- botstate_mutex: constants from backend.core.strategy_executor.helpers (_MAX_LOCK_RETRY_ATTEMPTS=4, _LOCK_RETRY_BASE_DELAY_SECONDS=0.2)
- Acceptance per file: pytest file -q → all passed.

### B2 API-drift fixture/assert updates (7 clusters, S each)
1. proposal_integration → patch backend.core.mode_context.get_context
2. genome low-confidence/integration → encode intentional fallback-edge behavior (fixture yes=0.3 signals by design)
3. genome empty-markets → fixture ctx.logger = MagicMock()
4. genome constants → MARKET_LIMIT==30, TOP_MARKETS_TO_PROCESS==50
5. orchestrator_wiring + config_integration → drop WHALE_LISTENER_ENABLED setattrs (flag removed; getattr default False)
6. auto_sell ×9 → _make_trade sets market_end_date=None; defaults tests read settings.AUTO_SELL_MAX_HOLD_SECONDS (env-driven, .env currently 1800) instead of hardcoding
7. fitness ×2 → expected 0.95/0.05 with regime_consistency/recent_win_rate terms documented inline
- Acceptance: each cluster's file passes standalone.

### B3 Order-dependent isolation: test_api_strategies (M)
- Change: reproduce polluter pairings via `pytest --randomly-seed`-style bisection (or -p no:randomly pairwise runs), add DB/singleton reset fixture where contamination proven.
- Acceptance: file passes BOTH standalone and inside full-suite run.

### B4 Whole-suite receipt
- Acceptance: `python -m pytest backend/tests -q` → **0 failed** (target ≥3452 passed).

## Phase C — Meteora dashboard surface (close the UX gap)

### C1 API contract freeze
- Change: none (verify only) — document the 4 endpoints + payload shapes in `docs/plans/` appendix from OpenAPI so the UI work targets a frozen contract.
- Acceptance: appendix committed; shapes match live TestClient responses.

### C2 Route + page scaffold
- Files: `frontend/src/App.tsx` (lazy route `/meteora`), new `frontend/src/pages/Meteora.tsx`, nav link in sidebar/menu component used by Dashboard shell.
- Change: page skeleton with three sections: Candidates table, Screen-now control, Cycle history.
- Acceptance: route renders at /meteora in dev server; nav entry visible.

### C3 Candidates table
- Change: TanStack Query hook → GET /api/v1/meteora/candidates?limit=100; columns pool/name, degen_score, weighted_score, 4 subscores (mini bars), rejected+reason filter toggle, created_at. Sorting by score desc default; include_rejected switch.
- Acceptance: renders fixture-backed data in vitest (msw or axios-mock) — component test asserting score sort + reject filter.

### C4 Screen-now control + cycle detail
- Change: POST /screen button with timeframe/category/page_size inputs (defaults 30m/trending/100), result banner (accepted/rejected counts), auto-refresh candidates query; clicking a cycle row opens GET /candidates/{cycle_id} drawer.
- Acceptance: vitest interaction test (button fires POST with params); manual curl parity check.

### C5 Vitest coverage for the page
- Change: `Meteora.test.tsx` covering render-empty, populated table, screen-now flow, error state.
- Acceptance: `npm run test -- --run Meteora` green; total suite still green.

### C6 Browser QA on live dev server
- Change: run vite dev (or preview of real build), drive with Playwright/console-error harness: navigate /meteora, click screen-now against backend running on :8100, screenshot candidates table, assert zero console errors.
- Acceptance: receipt = screenshot path + console-error count 0; add spec to playwright suite if pattern exists.

---

## Phase D — Env contract hygiene

### D1 Delete dead keys from .env.example
- Change: remove keys with zero consumers (verified list): DISABLED_STRATEGIES block, *_CONFIG suffixed twins (HFT_ENABLED_CONFIG, PAPER_SLIPPAGE_BPS_CONFIG, MAX_TIME_REMAINING_CONFIG, ...), POLLING_FAST_MS/SLOW/VERY_SLOW, LIMITLESS_WALLET_ADDRESS, INITIAL_BANKROLL_MANAGEMENT.
- Acceptance: for each removed key `grep -r "<KEY>" backend/ scripts/` → 0 hits (receipt listed).

### D2 Fix invalid example values
- Change: replace literal '...' placeholders (DRAWDOWN_BREAKER_ENABLED_PER_MODE, DAILY_LOSS_LIMIT_ENABLED_PER_MODE at .env.example:591-593) with valid JSON dicts matching Dict[str,bool] schema; move stray MIN_EDGE_PP above the copy-instruction comment header.
- Acceptance: `python -c "from backend.config import settings"` unaffected AND a jq/py parse of each edited line passes its type annotation.

### D3 Document soft-consumed keys (bounded sweep)
- Change: for the highest-traffic getattr-only keys (DAILY_LOSS_LIMIT_PCT, APEX_STALE_MIN_VOLUME, + top 10 more from the 306 gap list ranked by grep usage count), add commented entries with defaults to .env.example. Full 306 reconciliation explicitly OUT of scope (tracked as follow-up).
- Acceptance: each added key cites its consumer file:line as an inline comment.

---

## Phase E — Docs truthfulness

### E1 README strategy/platform claims sync
- Change: update "9 Active Strategies" list to current StrategyConfig reality (query DB seeds/scripts); keep "10+ platforms" (verified TRUE).
- Acceptance: every named strategy exists in codebase (grep class/file).

### E2 Root report-MD clutter quarantine
- Change: move dated one-off reports (POLYEDGE_PERFORMANCE_REPORT_2026-06-10.md, SELLABILITY-REPORT.md, STRATEGY_FIX_REPORT.md, VERIFICATION.md, PLATFORM_COVERAGE.md, POLYMARKET_TOP_TRADER_ANALYSIS.md, HACKATHON.md, audit_crash.py, dashboard-api.json) into `docs/archive/` (git mv, history preserved). Keep README/AGENTS/CLAUDE/CODEBASE/LICENSE/Procfile/Dockerfile at root.
- Acceptance: root *.md count ≤ 6; all moved files still tracked.

---

## Phase F — Final verification gates (definition of done)

### F1 Backend zero-failure receipt
- Full `pytest backend/tests -q` → 0 failed (≥3452 passed expected).

### F2 Frontend buildable + tested
- `npm run build` exit 0; vitest full run green incl. new Meteora tests.

### F3 End-to-end browser receipt
- Playwright sweep: dashboard pages load with 0 console errors, /meteora functional against live backend.

### F4 Close-out
- AGENTS.md module-map/docs touch-ups if any file moved; brain-save summary commit; tag suggestion `qa-green-YYYYMMDD`.

## Out-of-scope guardrails (explicit non-goals)
- No production deployment/docker changes beyond local build proof.
- No live-trading enablement (executor flags stay off).
- No refactors of god-files, no dependency upgrades, no PG runtime migration testing (separate track).
- Full 306-key env reconciliation deferred.

## Effort estimate
B0 0.5h · A ~0.5d · B ~1.5d (B3 is the long pole) · C ~0.5-1d · D ~2h · E ~1h · F ~0.5h ⇒ **≈3-4 focused days**.


---

# PLAN v2 ADDENDUM (2026-08-26 review) — supersedes ordering; adds Phases S & V

## Review findings driving v2
- SECURITY: /api/v1/meteora/* mounted WITHOUT require_admin — violates dominant repo convention (30+ routers). Fix S1.
- ROBUSTNESS: "closing" status has no recovery path (paper.py single occurrence, no sweep). Fix S2.
- OPS: zero retention on meteora_pool_snapshots/candidates/decisions (~5k snapshot rows/day incl. full payload JSON). Fix S3.
- ECONOMICS: executor DryRun validates shape only — no price-drift or duplicate-open guard. Fix S4.
- SUPPLY CHAIN: pip-audit installed but never run; npm audit never run. V1/V2.
- MEASUREMENT: no coverage baseline anywhere. V3.

## Phase S — Security & robustness hardening

### S1 Admin-auth on Meteora router
- Files: backend/api/meteora.py (router-level dependencies=[Depends(require_admin)]), new tests in test_meteora_api.py
- Change: router = APIRouter(prefix="/meteora", tags=["meteora"], dependencies=[Depends(require_admin)]); tests assert 401/403 without Authorization header and 200 with settings.ADMIN_API_KEY (conftest override path must inject the dependency context — follow existing admin-route test pattern).
- Acceptance: unauthenticated screen POST -> 401/403; authorized -> 200; all existing API tests updated to authed client fixture.

### S2 Zombie-"closing" recovery sweep
- Files: backend/data/meteora/paper.py (start of run_management_cycle), test_meteora_paper_learning.py
- Change: before evaluation loop, select paper positions status=="closing" AND updated older than 10 min (track via closed_at NULL + opened_at age or added swept_at col — prefer reusing minutes_held semantics: opened_at age check); force-close with reason "recovered".
- Acceptance: seeded stale closing row becomes closed with decision reason=recovered after one cycle.

### S3 Retention pruning job
- Files: backend/data/meteora/service.py (prune_expired_data(days) fn), scheduler registration id="meteora_retention" IntervalTrigger(hours=24), config mixin key METEORA_RETENTION_DAYS:int=30
- Change: delete from meteora_pool_snapshots/meteora_candidates/meteora_decisions where created_at < cutoff (lessons retained — small table).
- Acceptance: unit test inserts old+new rows, prune removes only old; registry contains meteora_retention.

### S4 Executor economic sanity + idempotency
- Files: backend/data/meteora/executor.py, tests
- Change: before builder.open_position: (a) fetch live pool price, reject if |entry_mid - live|/live > 0.03; (b) reject if an open live position with same pool_address+strategy exists (in addition to max count).
- Acceptance: three new tests (drift reject, duplicate reject, pass-through when clean).

## Phase V — Supply chain & measurement

### V1 pip-audit receipt
- Run: pip-audit -r requirements.txt --ignore-vuln EXCLUDED (if any, justify inline) > docs/plans/pip-audit-receipt.txt
- Acceptance: file committed; every CRITICAL/HIGH either patched (bump pin) or explicitly waived with reason.

### V2 npm audit receipt
- Run: cd frontend && npm audit --omit=dev --json > ../docs/plans/npm-audit-receipt.json
- Acceptance: file committed; criticals triaged same policy.

### V3 Coverage baseline
- Run: pytest backend/tests/test_meteora_client.py ..(all six).. --cov=backend/data/meteora --cov-report=term-missing
- Acceptance: >=85% line coverage on backend/data/meteora/*; repo-wide total number recorded in this file (no repo gate).

## Revised execution order
B0 -> A -> S -> B -> C (auth-aware client usage) -> V -> D -> E -> F
F-gate additions: S/V receipts exist; meteora coverage >=85%.

## Effort v2: ~4-4.5 focused days.


---

# CLOSE-OUT VERIFICATIONS (2026-08-26, post-green)

- **PG schema verified**: polyedge Postgres holds 101 public tables — `bot_state`,
  `trades`, and all `meteora_*` present; model↔DB table names match. (An interim
  "botstate missing" observation was a probe typo — `botstate` vs `bot_state`.)
- **Runtime/pin coherence**: importlib.metadata attests aiohttp 3.14.3,
  orjson 3.11.6, urllib3 2.7.0 — identical to requirements.txt pins; 107/107
  smoke executed on exactly this state; backend-8100 restarted onto it.
- **Scheduler registry**: all three meteora jobs present in
  JOB_FUNCTION_REGISTRY (screening/management/retention), membership asserted.
