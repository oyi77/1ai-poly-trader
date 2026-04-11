# PolyEdge: Full Codebase Completion Plan

## TL;DR

> **Quick Summary**: Fix every gap found during deep research to make PolyEdge a fully complete, production-ready prediction market trading bot. Covers broken frontend tests, drifted documentation, deprecation warnings, feature stubs, error handling, and production infrastructure.
> 
> **Deliverables**:
> - All frontend tests passing (currently 5 failures)
> - All documentation matching actual codebase
> - Zero deprecation warnings in backend (currently ~69k)
> - Feature stubs completed or explicitly de-scoped
> - Exception handling audited and improved across 77 backend files
> - Frontend bundle optimized (code splitting for 1.8MB+ chunks)
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: Task 1 (vitest config) → Task 5 (PendingApprovals test) → Task 19 (integration smoke test) → F1-F4

---

## Context

### Original Request
User asked for deep research to find all gaps in the PolyEdge codebase, then a comprehensive plan to fix everything to make a fully complete working codebase.

### Interview Summary
**Key Discussions**:
- No formal interview — the deep research phase was empirical (test runs, code scans, API contract verification, doc comparison)
- User confirmed intent: "create the comprehensive planning" based on research findings

**Research Findings**:
- **Backend**: 528/528 tests pass, but 69,348 deprecation warnings from Pydantic, SQLAlchemy, FastAPI, and asyncio
- **Frontend**: 5 test failures across 3 files (vitest picks up Playwright e2e files; PendingApprovals missing QueryClientProvider; OpportunityScanner and WhaleActivityFeed mock `fetch` instead of `axios`)
- **Frontend build**: Passes clean, but GlobeView.tsx chunk is 1.8MB, index.js is 950KB
- **Documentation**: ARCHITECTURE.md describes a completely different product; IMPLEMENTATION_GAPS.md falsely claims "100% Complete"; README.md partially accurate but has stale sections
- **Email notification**: Explicitly logged "not implemented" in `notification_router.py` line 117-122
- **Market maker**: Inventory tracking is placeholder (defaults to 0) in `market_maker.py` line 163
- **Exception handling**: 306 bare `except Exception` sites across 77 backend files, many silently swallowing errors
- **API contract**: Frontend-to-backend routes verified — no mismatches found
- **External integrations**: Polymarket CLOB follows official SDK; Kalshi API docs returned 404

### Metis Review (Self-Conducted)
**Identified Gaps** (addressed):
- Email notification: De-scope as explicit design choice (not a production priority; Telegram/Discord already work)
- Exception swallowing: Too large for "fix all 306" — prioritize critical paths (order execution, risk management, orchestrator)
- Kalshi API 404: Investigate in research task, don't assume broken
- Frontend test fixes must be validated by running `npm test` after each fix

---

## Work Objectives

### Core Objective
Close every gap identified during deep research so that PolyEdge has zero broken tests, accurate documentation, zero deprecation warnings, and hardened error handling on all critical paths.

### Concrete Deliverables
- `npm test` in frontend: 0 failures (currently 5)
- `npm run build` in frontend: passes with smaller bundles
- `pytest` in backend: 528/528 pass with <100 warnings (currently 69,348)
- ARCHITECTURE.md, README.md, IMPLEMENTATION_GAPS.md: accurate
- Critical-path exception handling: structured logging, no silent swallowing
- Email notification: explicitly de-scoped with code comment + docs note
- Market maker inventory: real tracking via database

### Definition of Done
- [ ] `cd frontend && npm test` → 0 failures, all pass
- [ ] `cd frontend && npm run build` → passes, no chunk >500KB
- [ ] `pytest --tb=short -q` → 528+ pass, 0 fail, <100 warnings
- [ ] `grep -r "from sqlalchemy.ext.declarative import" backend/` → 0 matches
- [ ] `grep -r "@app.on_event" backend/` → 0 matches
- [ ] `grep -r "asyncio.iscoroutinefunction" backend/` → 0 matches
- [ ] All 4 final verification agents approve

### Must Have
- All existing tests continue passing after changes
- No new runtime regressions (backend 528 tests still green)
- Documentation matches the actual file tree and feature set
- Critical-path error handlers log structured messages (not silent `pass`)

### Must NOT Have (Guardrails)
- Do NOT add new features beyond what's described in this plan
- Do NOT refactor code style/formatting that isn't related to a specific gap
- Do NOT modify trading logic or strategy parameters
- Do NOT touch `.env` or any credential files
- Do NOT change API endpoint contracts (frontend/backend compatibility verified)
- Do NOT add JSDoc/docstring comments beyond what's needed for the fix
- Do NOT install new npm/pip packages unless strictly required for a fix
- Do NOT create Alembic migrations in this plan (separate future work)
- Do NOT add Grafana dashboards in this plan (separate future work)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (backend: pytest; frontend: vitest + playwright)
- **Automated tests**: Tests-after (fix existing broken tests, add tests only where gaps are fixed)
- **Framework**: pytest (backend), vitest (frontend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend**: Use Bash (`npm test`, `npm run build`) — assert exit code 0, parse output for pass/fail counts
- **Backend**: Use Bash (`pytest`, `python -c "..."`) — assert exit code 0, parse warning counts
- **Documentation**: Use Bash (`grep`, `diff`) + Read tool — verify file references exist

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — test fixes + config, all independent):
├── Task 1: Fix vitest.config.ts to exclude e2e [quick]
├── Task 2: Fix OpportunityScanner.test.tsx mock [quick]
├── Task 3: Fix WhaleActivityFeed.test.tsx mock [quick]
├── Task 4: Fix PendingApprovals.test.tsx QueryClient wrapper [quick]
├── Task 5: Fix Pydantic Settings deprecated class Config [quick]
├── Task 6: Fix SQLAlchemy deprecated declarative_base import [quick]
├── Task 7: Fix FastAPI deprecated @app.on_event lifecycle [quick]
└── Task 8: Fix asyncio.iscoroutinefunction deprecation (3 files) [quick]

Wave 2 (After Wave 1 — documentation + feature stubs):
├── Task 9: Rewrite ARCHITECTURE.md to match actual codebase [writing]
├── Task 10: Rewrite IMPLEMENTATION_GAPS.md with accurate status [writing]
├── Task 11: Update README.md to match current reality [writing]
├── Task 12: De-scope email notification with explicit comments [quick]
├── Task 13: Implement real inventory tracking for market maker [deep]
└── Task 14: Fix unawaited CLOBWebSocket._send_subscribe coroutine [quick]

Wave 3 (After Wave 2 — exception handling audit on critical paths):
├── Task 15: Audit exception handling in core/orchestrator.py [unspecified-high]
├── Task 16: Audit exception handling in strategies/order_executor.py [unspecified-high]
├── Task 17: Audit exception handling in core/risk_manager.py [unspecified-high]
├── Task 18: Audit exception handling in core/strategy_executor.py [unspecified-high]
└── Task 19: Audit exception handling in api/main.py [unspecified-high]

Wave 4 (After Wave 3 — bundle optimization + final hardening):
├── Task 20: Frontend bundle code splitting (GlobeView lazy-load) [quick]
├── Task 21: Audit exception handling in data/polymarket_clob.py [unspecified-high]
└── Task 22: Audit exception handling in core/settlement_helpers.py [unspecified-high]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → npm test verification → Task 20 → F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 8 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 2, 3, 4 (vitest config must be right first) |
| 2 | 1 | — |
| 3 | 1 | — |
| 4 | 1 | — |
| 5 | — | 9, 10 |
| 6 | — | 9, 10 |
| 7 | — | 9, 10 |
| 8 | — | — |
| 9 | 5, 6, 7 | — |
| 10 | 5, 6, 7 | — |
| 11 | — | — |
| 12 | — | 10 |
| 13 | — | — |
| 14 | — | — |
| 15 | — | — |
| 16 | — | — |
| 17 | — | — |
| 18 | — | — |
| 19 | — | — |
| 20 | — | — |
| 21 | — | — |
| 22 | — | — |
| F1-F4 | ALL above | — |

### Agent Dispatch Summary

- **Wave 1**: **8 tasks** — T1-T8 → `quick`
- **Wave 2**: **6 tasks** — T9-T11 → `writing`, T12 → `quick`, T13 → `deep`, T14 → `quick`
- **Wave 3**: **5 tasks** — T15-T19 → `unspecified-high`
- **Wave 4**: **3 tasks** — T20 → `quick`, T21-T22 → `unspecified-high`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Fix vitest.config.ts to exclude e2e directory

  **What to do**:
  - Add `exclude` or `include` pattern to `frontend/vitest.config.ts` so Vitest only runs `src/test/**/*.test.{ts,tsx}` and ignores `e2e/**/*.spec.ts`
  - The current config (lines 1-11) has no include/exclude, so Vitest picks up Playwright spec files in `e2e/` and crashes with "test.describe() not expected here"
  - Add `include: ['src/**/*.test.{ts,tsx}']` to the `test` block

  **Must NOT do**:
  - Do NOT delete or modify any e2e test files
  - Do NOT change the test environment or setupFiles

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file, 1-line config change
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Not applicable — this is a config fix, not a feature

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5, 6, 7, 8)
  - **Blocks**: Tasks 2, 3, 4 (they depend on vitest config being correct first)
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `frontend/vitest.config.ts:1-11` — Current config with no include/exclude pattern. The `test` block at line 5-9 needs an `include` field added.

  **API/Type References**:
  - Vitest config docs: `include` field accepts glob patterns like `['src/**/*.test.{ts,tsx}']`

  **External References**:
  - Vitest docs: `https://vitest.dev/config/#include`

  **WHY Each Reference Matters**:
  - `vitest.config.ts` is the exact file to modify — the executor needs to see the current structure to add `include` correctly
  - The e2e directory `frontend/e2e/` contains 4 Playwright spec files that Vitest incorrectly picks up

  **Acceptance Criteria**:

  - [ ] `cd frontend && npx vitest run --reporter=verbose 2>&1 | tail -5` → shows 0 failures from e2e files
  - [ ] `grep -c "include" frontend/vitest.config.ts` → 1

  **QA Scenarios**:

  ```
  Scenario: Vitest runs only unit tests, not e2e specs
    Tool: Bash
    Preconditions: frontend/vitest.config.ts has include pattern
    Steps:
      1. Run: cd frontend && npx vitest run --reporter=verbose 2>&1
      2. Search output for "e2e/" — should NOT appear in test file list
      3. Assert exit code is 0 or only pre-existing test failures (not Playwright crashes)
    Expected Result: No "test.describe() not expected" errors; e2e files not listed in test run
    Failure Indicators: Output contains "Playwright" or "e2e/" file paths in test runner
    Evidence: .sisyphus/evidence/task-1-vitest-exclude-e2e.txt

  Scenario: e2e files still exist and are unchanged
    Tool: Bash
    Preconditions: e2e directory exists
    Steps:
      1. Run: ls frontend/e2e/*.spec.ts | wc -l
      2. Assert count >= 4
    Expected Result: e2e files are untouched (4+ spec files present)
    Failure Indicators: Files deleted or count is 0
    Evidence: .sisyphus/evidence/task-1-e2e-files-intact.txt
  ```

  **Commit**: YES (groups with Tasks 2, 3, 4)
  - Message: `fix(frontend): fix vitest config and broken test mocks`
  - Files: `frontend/vitest.config.ts`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 2. Fix OpportunityScanner.test.tsx to mock axios instead of fetch

  **What to do**:
  - Replace `vi.stubGlobal('fetch', ...)` with a proper mock of the `../api` module's `api.get()` method
  - The component (`OpportunityScanner.tsx` line 25) uses `api.get<{ opportunities: ArbOpportunity[] }>('/arbitrage/opportunities')` — NOT global `fetch`
  - Mock the `../api` module: `vi.mock('../api', () => ({ api: { get: vi.fn().mockResolvedValue({ data: { opportunities: [] } }) } }))`
  - The test asserts `screen.findByText(/No arbitrage opportunities/i)` which should work once the mock returns empty data correctly

  **Must NOT do**:
  - Do NOT modify `OpportunityScanner.tsx` component code
  - Do NOT change what the test asserts — only fix the mock

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single test file, straightforward mock replacement
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5, 6, 7, 8)
  - **Blocks**: None
  - **Blocked By**: Task 1 (vitest config must exclude e2e first)

  **References**:

  **Pattern References**:
  - `frontend/src/test/OpportunityScanner.test.tsx:1-16` — Current broken test mocking global `fetch` instead of axios `api.get()`
  - `frontend/src/components/OpportunityScanner.tsx:1-40` — Component uses `api.get<{ opportunities: ArbOpportunity[] }>('/arbitrage/opportunities')` at line 25
  - `frontend/src/test/PendingApprovals.test.tsx:5-9` — Reference for correct mock pattern: `vi.mock('../api', () => ({ ... }))`

  **WHY Each Reference Matters**:
  - The broken test shows the wrong mock (global fetch). The component shows the real API call (axios). PendingApprovals test shows the correct pattern to follow.

  **Acceptance Criteria**:

  - [ ] `cd frontend && npx vitest run src/test/OpportunityScanner.test.tsx` → PASS (1 test, 0 failures)

  **QA Scenarios**:

  ```
  Scenario: OpportunityScanner test passes with empty opportunities
    Tool: Bash
    Preconditions: vitest.config.ts excludes e2e (Task 1 complete)
    Steps:
      1. Run: cd frontend && npx vitest run src/test/OpportunityScanner.test.tsx --reporter=verbose 2>&1
      2. Assert output contains "1 passed" or "Tests: 1 passed"
      3. Assert exit code is 0
    Expected Result: Test passes, showing "No arbitrage opportunities" text found
    Failure Indicators: "FAIL" in output, exit code non-zero
    Evidence: .sisyphus/evidence/task-2-opportunity-scanner-test.txt

  Scenario: No global fetch mock remains in test file
    Tool: Bash
    Preconditions: Test file has been modified
    Steps:
      1. Run: grep -c "stubGlobal.*fetch" frontend/src/test/OpportunityScanner.test.tsx
      2. Assert count is 0
    Expected Result: No global fetch mocking in the file
    Failure Indicators: Count > 0
    Evidence: .sisyphus/evidence/task-2-no-global-fetch.txt
  ```

  **Commit**: YES (groups with Tasks 1, 3, 4)
  - Message: `fix(frontend): fix vitest config and broken test mocks`
  - Files: `frontend/src/test/OpportunityScanner.test.tsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 3. Fix WhaleActivityFeed.test.tsx to mock axios instead of fetch

  **What to do**:
  - Replace `vi.stubGlobal('fetch', ...)` with a proper mock of the `../api` module's `api.get()` method
  - The component (`WhaleActivityFeed.tsx` line 25) uses `api.get<WhaleTx[]>('/whales/transactions', { params: { limit: 20 } })` — NOT global `fetch`
  - Mock the `../api` module: `vi.mock('../api', () => ({ api: { get: vi.fn().mockResolvedValue({ data: [] }) } }))`
  - The test asserts `screen.findByText(/No recent whale trades/i)` which should work once the mock returns empty array correctly

  **Must NOT do**:
  - Do NOT modify `WhaleActivityFeed.tsx` component code
  - Do NOT change what the test asserts — only fix the mock

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single test file, straightforward mock replacement
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5, 6, 7, 8)
  - **Blocks**: None
  - **Blocked By**: Task 1 (vitest config must exclude e2e first)

  **References**:

  **Pattern References**:
  - `frontend/src/test/WhaleActivityFeed.test.tsx:1-16` — Current broken test mocking global `fetch` instead of axios `api.get()`
  - `frontend/src/components/WhaleActivityFeed.tsx:1-40` — Component uses `api.get<WhaleTx[]>('/whales/transactions', { params: { limit: 20 } })` at line 25
  - `frontend/src/test/PendingApprovals.test.tsx:5-9` — Reference for correct mock pattern

  **WHY Each Reference Matters**:
  - Same pattern as Task 2 — wrong mock type. The component uses axios, not fetch.

  **Acceptance Criteria**:

  - [ ] `cd frontend && npx vitest run src/test/WhaleActivityFeed.test.tsx` → PASS (1 test, 0 failures)

  **QA Scenarios**:

  ```
  Scenario: WhaleActivityFeed test passes with empty whale trades
    Tool: Bash
    Preconditions: vitest.config.ts excludes e2e (Task 1 complete)
    Steps:
      1. Run: cd frontend && npx vitest run src/test/WhaleActivityFeed.test.tsx --reporter=verbose 2>&1
      2. Assert output contains "1 passed"
      3. Assert exit code is 0
    Expected Result: Test passes, showing "No recent whale trades" text found
    Failure Indicators: "FAIL" in output, exit code non-zero
    Evidence: .sisyphus/evidence/task-3-whale-feed-test.txt

  Scenario: No global fetch mock remains in test file
    Tool: Bash
    Preconditions: Test file has been modified
    Steps:
      1. Run: grep -c "stubGlobal.*fetch" frontend/src/test/WhaleActivityFeed.test.tsx
      2. Assert count is 0
    Expected Result: No global fetch mocking in the file
    Failure Indicators: Count > 0
    Evidence: .sisyphus/evidence/task-3-no-global-fetch.txt
  ```

  **Commit**: YES (groups with Tasks 1, 2, 4)
  - Message: `fix(frontend): fix vitest config and broken test mocks`
  - Files: `frontend/src/test/WhaleActivityFeed.test.tsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 4. Fix PendingApprovals.test.tsx to wrap with QueryClientProvider

  **What to do**:
  - The `PendingApprovals` component (line 2, 14, 20) uses `useQuery` and `useQueryClient` from `@tanstack/react-query`, which requires a `QueryClientProvider` wrapper
  - The test (`PendingApprovals.test.tsx`) renders `<PendingApprovals />` directly without wrapping — crashes with "No QueryClient set"
  - Fix: Create a `QueryClient` instance in the test and wrap renders: `render(<QueryClientProvider client={queryClient}><PendingApprovals /></QueryClientProvider>)`
  - The api module is already correctly mocked (lines 5-9) — only the rendering wrapper is missing

  **Must NOT do**:
  - Do NOT change the api mocks — they are correct
  - Do NOT modify the PendingApprovals component itself

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single test file, add QueryClient wrapper to render calls
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5, 6, 7, 8)
  - **Blocks**: None
  - **Blocked By**: Task 1 (vitest config must exclude e2e first)

  **References**:

  **Pattern References**:
  - `frontend/src/test/PendingApprovals.test.tsx:1-58` — Full test file; renders without QueryClientProvider at lines 17, 37, 53
  - `frontend/src/pages/PendingApprovals.tsx:1-24` — Component uses `useQuery` at line 20 and `useQueryClient` at line 14
  - `frontend/package.json` — Has `@tanstack/react-query@5.17.9` as dependency

  **WHY Each Reference Matters**:
  - The test file shows 3 render calls that all need wrapping. The component shows the React Query hooks that require the provider. package.json confirms the library version.

  **Acceptance Criteria**:

  - [ ] `cd frontend && npx vitest run src/test/PendingApprovals.test.tsx` → PASS (3 tests, 0 failures)

  **QA Scenarios**:

  ```
  Scenario: PendingApprovals test suite passes all 3 tests
    Tool: Bash
    Preconditions: vitest.config.ts excludes e2e (Task 1 complete)
    Steps:
      1. Run: cd frontend && npx vitest run src/test/PendingApprovals.test.tsx --reporter=verbose 2>&1
      2. Assert output contains "3 passed" (empty state, approve trigger, error message)
      3. Assert exit code is 0
    Expected Result: All 3 PendingApprovals tests pass
    Failure Indicators: "No QueryClient set" error, "FAIL", exit code non-zero
    Evidence: .sisyphus/evidence/task-4-pending-approvals-test.txt

  Scenario: QueryClientProvider import exists in test file
    Tool: Bash
    Preconditions: Test file has been modified
    Steps:
      1. Run: grep -c "QueryClientProvider\|QueryClient" frontend/src/test/PendingApprovals.test.tsx
      2. Assert count >= 2 (import + usage)
    Expected Result: QueryClient and QueryClientProvider are imported and used
    Failure Indicators: Count is 0
    Evidence: .sisyphus/evidence/task-4-queryclient-present.txt
  ```

  **Commit**: YES (groups with Tasks 1, 2, 3)
  - Message: `fix(frontend): fix vitest config and broken test mocks`
  - Files: `frontend/src/test/PendingApprovals.test.tsx`
  - Pre-commit: `cd frontend && npx vitest run`

- [x] 5. Fix Pydantic Settings deprecated class Config

  **What to do**:
  - In `backend/config.py` line 183-184, replace inner `class Config: env_file = ".env"` with `model_config = ConfigDict(env_file=".env")` as a class attribute
  - Import `ConfigDict` from `pydantic_settings` (already imports `BaseSettings` from there)
  - This fixes thousands of Pydantic deprecation warnings that fire on every test

  **Must NOT do**:
  - Do NOT change any Settings field names or defaults
  - Do NOT change the env variable names
  - Do NOT modify the `model_validator` or computed properties

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file, 3-line change (remove class Config, add model_config)
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4, 6, 7, 8)
  - **Blocks**: Tasks 9, 10 (docs need to know the fix happened)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/config.py:183-187` — Current deprecated `class Config: env_file = ".env"` inside `Settings(BaseSettings)`
  - `backend/config.py:1-8` — Imports section; `pydantic_settings` already imported for `BaseSettings`

  **External References**:
  - Pydantic v2 migration guide: Use `model_config = ConfigDict(...)` instead of inner `class Config`

  **WHY Each Reference Matters**:
  - Lines 183-184 are the exact code to change. The import section shows where to add `ConfigDict` import.

  **Acceptance Criteria**:

  - [ ] `pytest backend/tests/test_api_health.py -v --tb=short 2>&1 | grep -c "PydanticDeprecatedSince20"` → 0
  - [ ] `python -c "from backend.config import settings; print(settings.DATABASE_URL)"` → prints default DB URL without warnings

  **QA Scenarios**:

  ```
  Scenario: Settings loads without Pydantic deprecation warnings
    Tool: Bash
    Preconditions: config.py has been modified
    Steps:
      1. Run: python -W error::DeprecationWarning -c "from backend.config import settings; print(settings.TRADING_MODE)" 2>&1
      2. Assert output contains "paper" (default trading mode)
      3. Assert NO DeprecationWarning in output
    Expected Result: Settings loads cleanly, prints "paper"
    Failure Indicators: DeprecationWarning, ImportError, or traceback
    Evidence: .sisyphus/evidence/task-5-pydantic-config.txt

  Scenario: Backend tests still pass after config change
    Tool: Bash
    Preconditions: config.py modified
    Steps:
      1. Run: pytest backend/tests/test_api_health.py -v --tb=short -q 2>&1 | tail -5
      2. Assert "passed" in output, no "failed"
    Expected Result: Health check tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-5-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 6, 7, 8)
  - Message: `fix(backend): resolve deprecation warnings in config, models, api, core`
  - Files: `backend/config.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 6. Fix SQLAlchemy deprecated declarative_base import

  **What to do**:
  - In `backend/models/database.py` line 22, change `from sqlalchemy.ext.declarative import declarative_base` to `from sqlalchemy.orm import declarative_base`
  - This is the SQLAlchemy 2.0 migration: the function moved from `ext.declarative` to `orm`
  - No other code changes needed — the `Base = declarative_base()` call on the line after stays the same

  **Must NOT do**:
  - Do NOT change the Base variable name or usage
  - Do NOT modify any ORM model definitions
  - Do NOT change engine/session configuration

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single import line change
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-5, 7, 8)
  - **Blocks**: Tasks 9, 10 (docs reference this fix)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/models/database.py:22` — `from sqlalchemy.ext.declarative import declarative_base` (deprecated)
  - `backend/models/database.py:6-24` — Full imports section for context

  **External References**:
  - SQLAlchemy 2.0 migration: `declarative_base` moved to `sqlalchemy.orm`

  **WHY Each Reference Matters**:
  - Line 22 is the exact line to change. Context shows other imports remain unchanged.

  **Acceptance Criteria**:

  - [ ] `grep "from sqlalchemy.ext.declarative import" backend/models/database.py` → 0 matches
  - [ ] `grep "from sqlalchemy.orm import declarative_base" backend/models/database.py` → 1 match
  - [ ] `pytest backend/tests/ -q --tb=short 2>&1 | tail -3` → all pass

  **QA Scenarios**:

  ```
  Scenario: Database models load without SQLAlchemy deprecation warning
    Tool: Bash
    Preconditions: database.py import changed
    Steps:
      1. Run: python -W error::DeprecationWarning -c "from backend.models.database import Base, Signal, Trade; print('OK')" 2>&1
      2. Assert output contains "OK"
      3. Assert NO DeprecationWarning
    Expected Result: Models load cleanly
    Failure Indicators: DeprecationWarning or import error
    Evidence: .sisyphus/evidence/task-6-sqlalchemy-import.txt

  Scenario: All backend tests still pass
    Tool: Bash
    Preconditions: database.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output, "0 failed" or no "failed"
    Expected Result: 528+ tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-6-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 5, 7, 8)
  - Message: `fix(backend): resolve deprecation warnings in config, models, api, core`
  - Files: `backend/models/database.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 7. Fix FastAPI deprecated @app.on_event lifecycle to use lifespan

  **What to do**:
  - In `backend/api/main.py`, replace the `@app.on_event("startup")` handler (line 263) and `@app.on_event("shutdown")` handler (line 335) with a single `@asynccontextmanager` lifespan function
  - Import `from contextlib import asynccontextmanager` at the top of the file
  - Create `async def lifespan(app): ...` that yields between startup and shutdown logic
  - Pass `lifespan=lifespan` to the `FastAPI()` constructor
  - Move ALL startup logic (lines 264-332) into the "before yield" section
  - Move ALL shutdown logic (lines 336-344+) into the "after yield" section
  - Remove both `@app.on_event` decorated functions entirely

  **Must NOT do**:
  - Do NOT change any startup/shutdown logic — only restructure into lifespan
  - Do NOT modify any API routes, middleware, or CORS settings
  - Do NOT change the FastAPI constructor parameters other than adding `lifespan`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file restructuring, well-documented migration pattern
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Config migration, not a feature

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-6, 8)
  - **Blocks**: Tasks 9, 10 (docs reference this fix)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/api/main.py:262-344` — Current `@app.on_event("startup")` (line 263) and `@app.on_event("shutdown")` (line 335) with full startup/shutdown logic between them
  - `backend/api/main.py:1-30` — Import section where `from contextlib import asynccontextmanager` should be added

  **External References**:
  - FastAPI lifespan docs: `https://fastapi.tiangolo.com/advanced/events/#lifespan`
  - Pattern: `@asynccontextmanager async def lifespan(app): <startup>; yield; <shutdown>`

  **WHY Each Reference Matters**:
  - Lines 262-344 contain the exact startup and shutdown code to restructure. The import section shows where to add the new import. The FastAPI docs show the target pattern.

  **Acceptance Criteria**:

  - [ ] `grep -c "@app.on_event" backend/api/main.py` → 0
  - [ ] `grep -c "asynccontextmanager" backend/api/main.py` → 1
  - [ ] `grep -c "lifespan" backend/api/main.py` → at least 2 (definition + FastAPI constructor)
  - [ ] `pytest backend/tests/test_api_health.py -v --tb=short` → all pass

  **QA Scenarios**:

  ```
  Scenario: FastAPI app starts without @app.on_event deprecation warnings
    Tool: Bash
    Preconditions: main.py refactored to use lifespan
    Steps:
      1. Run: python -W error::DeprecationWarning -c "from backend.api.main import app; print(type(app))" 2>&1
      2. Assert output contains "<class 'fastapi.applications.FastAPI'>"
      3. Assert NO DeprecationWarning in output
    Expected Result: App imports cleanly without deprecation warnings
    Failure Indicators: DeprecationWarning about on_event, ImportError
    Evidence: .sisyphus/evidence/task-7-lifespan-import.txt

  Scenario: Health endpoint still works after lifespan migration
    Tool: Bash
    Preconditions: main.py refactored
    Steps:
      1. Run: pytest backend/tests/test_api_health.py -v --tb=short 2>&1
      2. Assert all tests pass
    Expected Result: Health check tests pass — startup logic runs correctly via lifespan
    Failure Indicators: Any test failure, "startup" or "shutdown" errors
    Evidence: .sisyphus/evidence/task-7-health-tests.txt

  Scenario: No @app.on_event remains in codebase
    Tool: Bash
    Preconditions: main.py refactored
    Steps:
      1. Run: grep -rn "@app.on_event" backend/api/main.py
      2. Assert exit code is 1 (no matches)
    Expected Result: Zero occurrences of deprecated pattern
    Failure Indicators: Any match found
    Evidence: .sisyphus/evidence/task-7-no-on-event.txt
  ```

  **Commit**: YES (groups with Tasks 5, 6, 8)
  - Message: `fix(backend): resolve deprecation warnings in config, models, api, core`
  - Files: `backend/api/main.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 8. Fix asyncio.iscoroutinefunction deprecation in 3 files

  **What to do**:
  - In Python 3.12+, `asyncio.iscoroutinefunction` is deprecated in favor of `inspect.iscoroutinefunction`
  - Fix these 3 files:
    1. `backend/core/retry.py:20` — Change `asyncio.iscoroutinefunction(func)` to `inspect.iscoroutinefunction(func)` and add `import inspect` at top
    2. `backend/core/errors.py:205` — Change `asyncio.iscoroutinefunction(func)` to `inspect.iscoroutinefunction(func)` and add `import inspect` at top
    3. `backend/ai/sentiment_analyzer.py:46` — Change `asyncio.iscoroutinefunction(self.client.complete)` to `inspect.iscoroutinefunction(self.client.complete)` and add `import inspect` at top
  - Keep `import asyncio` in all files — it's still used for other asyncio operations (sleep, get_running_loop, etc.)

  **Must NOT do**:
  - Do NOT remove `import asyncio` — other asyncio functions are still used
  - Do NOT change any logic besides the `iscoroutinefunction` call

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3 files, identical 1-line change per file + 1 import addition
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-7)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/core/retry.py:20` — `if asyncio.iscoroutinefunction(func):` in `retry()` decorator
  - `backend/core/errors.py:205` — `if asyncio.iscoroutinefunction(func):` in error handler decorator
  - `backend/ai/sentiment_analyzer.py:46` — `if hasattr(self.client, "complete") and asyncio.iscoroutinefunction(self.client.complete):`

  **WHY Each Reference Matters**:
  - Each line shows the exact deprecated call to replace. The `import inspect` addition goes at the top of each file.

  **Acceptance Criteria**:

  - [ ] `grep -rn "asyncio.iscoroutinefunction" backend/` → 0 matches
  - [ ] `grep -rn "inspect.iscoroutinefunction" backend/` → 3 matches (one per file)
  - [ ] `pytest backend/tests/ -q --tb=short 2>&1 | tail -3` → all pass

  **QA Scenarios**:

  ```
  Scenario: No asyncio.iscoroutinefunction usage remains
    Tool: Bash
    Preconditions: All 3 files modified
    Steps:
      1. Run: grep -rn "asyncio.iscoroutinefunction" backend/
      2. Assert exit code is 1 (no matches)
    Expected Result: Zero occurrences of deprecated pattern
    Failure Indicators: Any match found
    Evidence: .sisyphus/evidence/task-8-no-asyncio-iscoro.txt

  Scenario: inspect.iscoroutinefunction used correctly in all 3 files
    Tool: Bash
    Preconditions: All 3 files modified
    Steps:
      1. Run: grep -rn "inspect.iscoroutinefunction" backend/core/retry.py backend/core/errors.py backend/ai/sentiment_analyzer.py
      2. Assert 3 lines of output (one per file)
    Expected Result: Each file uses inspect.iscoroutinefunction
    Failure Indicators: Count != 3
    Evidence: .sisyphus/evidence/task-8-inspect-iscoro.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: All 3 files modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output, no "failed"
    Expected Result: 528+ tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-8-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 5, 6, 7)
  - Message: `fix(backend): resolve deprecation warnings in config, models, api, core`
  - Files: `backend/core/retry.py`, `backend/core/errors.py`, `backend/ai/sentiment_analyzer.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 9. Rewrite ARCHITECTURE.md to match actual codebase

  **What to do**:
  - The current `ARCHITECTURE.md` describes a completely different product (weather+economics Kalshi bot with a nonexistent file tree like `kalshi_bot/`, `models/weather_model.py`, etc.)
  - Rewrite from scratch to accurately describe PolyEdge's actual architecture:
    - **System overview**: Automated prediction market trading bot targeting Polymarket and Kalshi
    - **Directory structure**: `backend/` (FastAPI + trading engine), `frontend/` (React dashboard), `docs/`, `tests/`
    - **Core components**: Orchestrator → Strategies → Signal Generation → Risk Manager → Order Executor → Settlement
    - **Data flow**: Market data feeds (CLOB, Kalshi, crypto, weather) → AI signal analysis → Strategy execution → Dashboard SSE
    - **Infrastructure**: SQLite/PostgreSQL, Redis (optional), APScheduler, WebSockets
    - **Deployment**: Docker Compose, Railway (backend), Vercel (frontend), PM2
  - Use the AGENTS.md hierarchy as authoritative source for what exists
  - Include an ASCII diagram similar to README.md but with more backend detail
  - Keep it under 200 lines — concise architecture overview, not exhaustive docs

  **Must NOT do**:
  - Do NOT invent features or files that don't exist
  - Do NOT copy README.md verbatim — ARCHITECTURE.md should be more technical/structural
  - Do NOT include configuration details (that's in docs/configuration.md)

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Full document rewrite requiring understanding of codebase structure
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `agent-docs`: This is human-facing architecture docs, not agent-facing

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 10, 11, 12, 13, 14)
  - **Blocks**: None
  - **Blocked By**: Tasks 5, 6, 7 (must know deprecation fixes landed to document accurately)

  **References**:

  **Pattern References**:
  - `AGENTS.md` (root) — Authoritative project overview: purpose, key files, subdirectory descriptions
  - `backend/AGENTS.md` — Detailed backend architecture: modules, strategies, data flows, dependencies
  - `backend/core/AGENTS.md` — Core trading logic description: signals, risk, execution, settlement
  - `backend/data/AGENTS.md` — Data layer: CLOB, Kalshi, crypto feeds, websockets, aggregator
  - `backend/api/AGENTS.md` — API layer: routes, WebSocket managers, auth

  **External References**:
  - `README.md` — Current ASCII architecture diagram (partially accurate, can be improved)
  - `docs/` directory — Existing detailed docs (api.md, how-it-works.md, configuration.md)

  **WHY Each Reference Matters**:
  - The AGENTS.md files are the ground truth for what exists. README has the only existing diagram. The executor needs these to write accurate architecture docs without hallucinating features.

  **Acceptance Criteria**:

  - [ ] `wc -l ARCHITECTURE.md` → between 80 and 200 lines
  - [ ] `grep -c "kalshi_bot/" ARCHITECTURE.md` → 0 (old fake directory gone)
  - [ ] `grep -c "weather_model.py" ARCHITECTURE.md` → 0 (old fake file gone)
  - [ ] Every directory mentioned in ARCHITECTURE.md actually exists (agent verifies with `ls`)

  **QA Scenarios**:

  ```
  Scenario: All file/directory references in ARCHITECTURE.md exist
    Tool: Bash
    Preconditions: ARCHITECTURE.md rewritten
    Steps:
      1. Extract all paths that look like file/directory references from ARCHITECTURE.md
      2. For each extracted path, run: ls -d <path> or test -e <path>
      3. Assert all referenced paths exist
    Expected Result: Zero dangling references
    Failure Indicators: Any "No such file or directory" errors
    Evidence: .sisyphus/evidence/task-9-arch-refs-valid.txt

  Scenario: No references to old fake product remain
    Tool: Bash
    Preconditions: ARCHITECTURE.md rewritten
    Steps:
      1. Run: grep -ciE "kalshi_bot|weather_model|economics" ARCHITECTURE.md
      2. Assert count is 0
    Expected Result: Old product description completely removed
    Failure Indicators: Any match to old product terminology
    Evidence: .sisyphus/evidence/task-9-no-old-refs.txt
  ```

  **Commit**: YES (groups with Tasks 10, 11)
  - Message: `docs: rewrite ARCHITECTURE.md, IMPLEMENTATION_GAPS.md, README.md to match reality`
  - Files: `ARCHITECTURE.md`
  - Pre-commit: none

- [x] 10. Rewrite IMPLEMENTATION_GAPS.md with accurate status

  **What to do**:
  - The current `IMPLEMENTATION_GAPS.md` falsely claims "100% Complete" for every category
  - Rewrite to honestly document:
    - **Completed**: What actually works (528 backend tests passing, React dashboard, all strategies executing, CLOB integration, settlement engine)
    - **Known limitations**: Email notification not implemented (de-scoped by design), market maker inventory is placeholder, 306 bare except blocks in 77 files (only critical paths audited), bundle size not optimized
    - **Future work**: Alembic migrations, Grafana dashboards, full exception handling coverage beyond critical paths, Kalshi live trading (API returns 404)
  - Structure: Organized by component (backend, frontend, infrastructure, monitoring)
  - Be honest about what's production-ready vs. what's development-quality

  **Must NOT do**:
  - Do NOT claim anything is "100% Complete" unless it truly is
  - Do NOT list features that don't exist
  - Do NOT create a roadmap — just document current gaps

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Full document rewrite requiring accurate status assessment
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9, 11, 12, 13, 14)
  - **Blocks**: None
  - **Blocked By**: Tasks 5, 6, 7, 12 (must know what was fixed/de-scoped to document accurately)

  **References**:

  **Pattern References**:
  - `IMPLEMENTATION_GAPS.md` — Current file to replace (falsely claims 100% complete everywhere)
  - `AGENTS.md` (root) — Ground truth for project structure and feature set
  - `backend/AGENTS.md` — Detailed feature inventory (strategies, data feeds, AI, monitoring)

  **WHY Each Reference Matters**:
  - The current file shows what categories to cover. The AGENTS.md files show what actually exists vs. what's placeholder.

  **Acceptance Criteria**:

  - [ ] `grep -c "100% Complete" IMPLEMENTATION_GAPS.md` → 0 (no blanket claims)
  - [ ] File mentions "email notification" as explicitly de-scoped
  - [ ] File mentions market maker inventory as placeholder

  **QA Scenarios**:

  ```
  Scenario: No false "100% Complete" claims
    Tool: Bash
    Preconditions: IMPLEMENTATION_GAPS.md rewritten
    Steps:
      1. Run: grep -ci "100%" IMPLEMENTATION_GAPS.md
      2. Assert count is 0
    Expected Result: No blanket completion claims
    Failure Indicators: Any "100%" match
    Evidence: .sisyphus/evidence/task-10-no-false-claims.txt

  Scenario: Known gaps are documented
    Tool: Bash
    Preconditions: IMPLEMENTATION_GAPS.md rewritten
    Steps:
      1. Run: grep -ciE "email|inventory|exception|bundle" IMPLEMENTATION_GAPS.md
      2. Assert count >= 3 (at least email, inventory, and exception handling mentioned)
    Expected Result: Major known gaps are documented
    Failure Indicators: Count < 3
    Evidence: .sisyphus/evidence/task-10-gaps-documented.txt
  ```

  **Commit**: YES (groups with Tasks 9, 11)
  - Message: `docs: rewrite ARCHITECTURE.md, IMPLEMENTATION_GAPS.md, README.md to match reality`
  - Files: `IMPLEMENTATION_GAPS.md`
  - Pre-commit: none

- [x] 11. Update README.md to match current reality

  **What to do**:
  - README.md is partially accurate but has stale sections
  - Update the following sections while preserving the overall structure:
    - **Title/badges**: Keep as-is (already accurate)
    - **Overview**: Update to reflect full feature set (not just BTC + weather — also includes market making, copy trading, arbitrage, whale tracking, AI ensemble)
    - **Architecture diagram**: Update ASCII diagram to include missing components (AI layer, queue system, monitoring)
    - **Quick Start**: Verify commands are correct, add any missing steps
    - **Documentation links**: Verify all doc links point to existing files
  - Do NOT rewrite from scratch — this is an UPDATE, not a rewrite
  - Keep the existing good content (badges, strategy descriptions, quick start format)

  **Must NOT do**:
  - Do NOT change the MIT license section
  - Do NOT remove strategy descriptions that are accurate
  - Do NOT add installation steps for features not in the codebase

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Targeted document update, need to diff existing vs. reality
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9, 10, 12, 13, 14)
  - **Blocks**: None
  - **Blocked By**: None (README update is independent of code fixes)

  **References**:

  **Pattern References**:
  - `README.md` — Current file to update (read entirely for context)
  - `AGENTS.md` (root) — Ground truth for project structure
  - `docs/` — Verify all documentation links are valid

  **WHY Each Reference Matters**:
  - README is the file to modify. AGENTS.md provides the truth. docs/ validates link targets.

  **Acceptance Criteria**:

  - [ ] All documentation links in README.md point to existing files
  - [ ] ASCII architecture diagram mentions backend, frontend, data sources, AI layer
  - [ ] Quick Start commands work (already verified — just check they're still accurate)

  **QA Scenarios**:

  ```
  Scenario: All documentation links resolve to existing files
    Tool: Bash
    Preconditions: README.md updated
    Steps:
      1. Extract all relative markdown links from README.md (pattern: [text](path))
      2. For each link, check file exists: test -f <path>
      3. Assert all links resolve
    Expected Result: Zero broken internal links
    Failure Indicators: Any "No such file" errors
    Evidence: .sisyphus/evidence/task-11-readme-links.txt

  Scenario: No references to nonexistent features
    Tool: Bash
    Preconditions: README.md updated
    Steps:
      1. Run: grep -ciE "kalshi_bot/|weather_model" README.md
      2. Assert count is 0
    Expected Result: No fake file/module references
    Failure Indicators: Any match
    Evidence: .sisyphus/evidence/task-11-no-fake-refs.txt
  ```

  **Commit**: YES (groups with Tasks 9, 10)
  - Message: `docs: rewrite ARCHITECTURE.md, IMPLEMENTATION_GAPS.md, README.md to match reality`
  - Files: `README.md`
  - Pre-commit: none

- [x] 12. De-scope email notification with explicit comments and docs note

  **What to do**:
  - In `backend/bot/notification_router.py:117-123`, the `_send_email` method is a placeholder that just logs "not implemented"
  - Update the method to:
    1. Add a clear docstring: `"""Email notifications are intentionally de-scoped. Telegram and Discord channels are the supported notification methods. See IMPLEMENTATION_GAPS.md."""`
    2. Change the log level from `logger.info` to `logger.debug` (reduce log noise in production)
    3. Raise `NotImplementedError("Email notifications de-scoped — use Telegram or Discord")` so callers get a clear error if they attempt email
  - This makes the de-scope decision explicit in code rather than a silent no-op

  **Must NOT do**:
  - Do NOT implement email sending (explicitly de-scoped)
  - Do NOT remove the method entirely (callers may reference it)
  - Do NOT change any other notification channels (Telegram, Discord)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 5-line change in one method
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9-11, 13, 14)
  - **Blocks**: Task 10 (IMPLEMENTATION_GAPS.md should mention this de-scope)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/bot/notification_router.py:117-123` — Current placeholder `_send_email` method that silently logs and returns

  **WHY Each Reference Matters**:
  - The method is the exact target. The executor needs to see the current implementation to add the docstring and raise.

  **Acceptance Criteria**:

  - [ ] `grep -c "NotImplementedError" backend/bot/notification_router.py` → 1
  - [ ] `grep -c "de-scoped\|de_scoped" backend/bot/notification_router.py` → at least 1
  - [ ] `pytest backend/tests/ -q --tb=short 2>&1 | tail -3` → all pass

  **QA Scenarios**:

  ```
  Scenario: Email notification raises NotImplementedError
    Tool: Bash
    Preconditions: notification_router.py modified
    Steps:
      1. Run: python -c "
      import asyncio
      from backend.bot.notification_router import NotificationRouter
      router = NotificationRouter()
      try:
          asyncio.run(router._send_email({'to': 'test@test.com'}, 'test'))
          print('ERROR: should have raised')
      except NotImplementedError as e:
          print(f'OK: {e}')
      " 2>&1
      2. Assert output starts with "OK:"
    Expected Result: NotImplementedError raised with de-scope message
    Failure Indicators: "ERROR: should have raised" or any other exception
    Evidence: .sisyphus/evidence/task-12-email-descoped.txt
  ```

  **Commit**: YES (groups with Tasks 13, 14)
  - Message: `fix(backend): de-scope email notification, fix market maker inventory, fix CLOB websocket`
  - Files: `backend/bot/notification_router.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 13. Implement real inventory tracking for market maker strategy

  **What to do**:
  - In `backend/strategies/market_maker.py:163-166`, inventory is read from `meta.get("current_inventory_usd", 0.0)` which always defaults to 0 since no market metadata provider populates this field
  - Replace the placeholder with real inventory tracking:
    1. Query the database for existing open positions in the current market: `SELECT SUM(size) FROM trades WHERE market_ticker = ? AND status = 'open' AND strategy = 'market_maker'`
    2. Use the aggregated position size as `current_inventory`
    3. The `ctx.db` (SQLAlchemy session) is available on the `StrategyContext` passed to `run_cycle`
    4. Import `Trade` model from `backend.models.database`
  - Keep the `max_inventory` parameter from strategy params (already read from `params.get("max_inventory_usd", 500.0)` at the top of `run_cycle`)
  - Keep the `inventory_pct` calculation and clamping logic

  **Must NOT do**:
  - Do NOT change spread calculation logic
  - Do NOT change quote generation logic
  - Do NOT modify the CycleResult return structure
  - Do NOT change strategy parameters or defaults

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding the database model, trade status lifecycle, and strategy context
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Existing tests should still pass; we're fixing a placeholder, not adding a new feature

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9-12, 14)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/strategies/market_maker.py:148-177` — Market iteration loop showing inventory placeholder at line 163-166 and how `inventory_pct` feeds into `calculate_spread()` and `calculate_quotes()`
  - `backend/strategies/base.py` — `StrategyContext` dataclass with `db` (SQLAlchemy session), `settings`, `params`
  - `backend/models/database.py` — `Trade` model with `market_ticker`, `status`, `size`, `strategy_name` fields
  - `backend/strategies/market_maker.py:1-30` — Imports section and class definition

  **WHY Each Reference Matters**:
  - Lines 148-177 show the exact code to modify. base.py shows the `ctx.db` available for querying. database.py shows the Trade model fields for the position query.

  **Acceptance Criteria**:

  - [ ] `grep -c "current_inventory_usd" backend/strategies/market_maker.py` → 0 (placeholder metadata key removed)
  - [ ] `grep -c "ctx.db" backend/strategies/market_maker.py` → at least 1 (uses database for inventory)
  - [ ] `pytest backend/tests/ -q --tb=short 2>&1 | tail -3` → all pass

  **QA Scenarios**:

  ```
  Scenario: Market maker queries database for inventory instead of placeholder
    Tool: Bash
    Preconditions: market_maker.py modified
    Steps:
      1. Run: grep -n "current_inventory_usd" backend/strategies/market_maker.py
      2. Assert exit code is 1 (no matches — placeholder key gone)
      3. Run: grep -n "ctx.db\|db.query\|db.execute" backend/strategies/market_maker.py
      4. Assert at least 1 match (database query used)
    Expected Result: Inventory comes from database, not metadata placeholder
    Failure Indicators: Placeholder key still present, or no database usage
    Evidence: .sisyphus/evidence/task-13-inventory-tracking.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: market_maker.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output, no "failed"
    Expected Result: 528+ tests pass (market maker tests included)
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-13-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 12, 14)
  - Message: `fix(backend): de-scope email notification, fix market maker inventory, fix CLOB websocket`
  - Files: `backend/strategies/market_maker.py`
  - Pre-commit: `pytest --tb=short -q`

- [x] 14. Fix unawaited CLOBWebSocket._send_subscribe coroutine

  **What to do**:
  - In `backend/data/ws_client.py:72-76`, the `subscribe()` method is synchronous but calls `asyncio.create_task(self._send_subscribe({token_id}))` at line 76
  - This can raise `RuntimeError: no running event loop` if called outside an async context, or silently fail if the task is never awaited
  - Fix: Make `subscribe()` an async method and use `await self._send_subscribe({token_id})` instead of `asyncio.create_task()`
  - Note: `backend/data/orderbook_ws.py:148-149` already does this correctly — `subscribe()` is `async def` and uses `await self._send_subscribe({token_id})`
  - Check all callers of `ws_client.subscribe()` — they must now `await` it. If any are synchronous callers, they need to be wrapped with `asyncio.create_task()` at the call site (which is correct — the caller decides the scheduling, not the method itself)

  **Must NOT do**:
  - Do NOT modify `orderbook_ws.py` — it already handles this correctly
  - Do NOT change the `_send_subscribe` implementation
  - Do NOT add try/except around the subscription call

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small async fix in one file, well-understood pattern
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 9-13)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `backend/data/ws_client.py:72-76` — Sync `subscribe()` with `asyncio.create_task(self._send_subscribe(...))` at line 76 (the bug)
  - `backend/data/orderbook_ws.py:143-149` — Correct pattern: async `subscribe()` with `await self._send_subscribe(...)` at line 149
  - `backend/data/ws_client.py:158` — `_send_subscribe` is properly async, just needs to be awaited

  **WHY Each Reference Matters**:
  - ws_client.py:72-76 is the bug. orderbook_ws.py:143-149 is the correct pattern to follow. The executor needs both to see the before/after.

  **Acceptance Criteria**:

  - [ ] `grep -c "asyncio.create_task.*_send_subscribe" backend/data/ws_client.py` → 0
  - [ ] `grep -c "await self._send_subscribe" backend/data/ws_client.py` → at least 1
  - [ ] `pytest backend/tests/ -q --tb=short 2>&1 | tail -3` → all pass

  **QA Scenarios**:

  ```
  Scenario: ws_client.subscribe is async and awaits _send_subscribe
    Tool: Bash
    Preconditions: ws_client.py modified
    Steps:
      1. Run: grep -A5 "def subscribe" backend/data/ws_client.py | head -6
      2. Assert first line contains "async def subscribe"
      3. Run: grep -c "asyncio.create_task.*_send_subscribe" backend/data/ws_client.py
      4. Assert count is 0
    Expected Result: subscribe() is async, directly awaits _send_subscribe
    Failure Indicators: Missing "async", or create_task pattern still present
    Evidence: .sisyphus/evidence/task-14-ws-subscribe-fix.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: ws_client.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output, no "failed"
    Expected Result: 528+ tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-14-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 12, 13)
  - Message: `fix(backend): de-scope email notification, fix market maker inventory, fix CLOB websocket`
  - Files: `backend/data/ws_client.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 15. Audit Exception Handling in core/orchestrator.py

  **What to do**:
  - Open `backend/core/orchestrator.py` and locate all 9 bare `except Exception` sites
  - For each site, classify the handler intent:
    - **Graceful degradation** (exception swallowed intentionally) → keep swallowing, add structured log: `logger.error(f"[orchestrator.{func_name}] {type(e).__name__}: {e}", exc_info=True)`
    - **Re-raise after logging** → add structured log before the raise
    - **Narrowable** (e.g., catching `Exception` when only `ConnectionError`/`TimeoutError` possible) → narrow the type AND add structured log
  - Every modified `except` block must include: module name (`orchestrator`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite to confirm zero regressions

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change error handling semantics (if it swallowed before, keep swallowing)
  - Do NOT modify any business/trading logic
  - Do NOT remove any existing error handling
  - Do NOT add overly verbose docstrings or comments

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic file audit requiring careful semantic analysis of each exception site
  - **Skills**: []
    - No specialized skills needed — pure code analysis and targeted edits
  - **Skills Evaluated but Omitted**:
    - `systematic-debugging`: Not debugging a bug, just improving exception logging

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 16, 17, 18, 19)
  - **Blocks**: F1, F2, F3, F4 (Final Verification)
  - **Blocked By**: None (can start after Wave 2)

  **References**:

  **Pattern References** (existing code to follow):
  - `backend/core/orchestrator.py` — Full file; all 9 bare `except Exception` sites are targets

  **External References**:
  - Python logging best practices: structured logging with `exc_info=True` for tracebacks

  **WHY Each Reference Matters**:
  - The orchestrator is the central coordination module — unstructured error logs here make debugging production trading failures extremely difficult

  **Acceptance Criteria**:
  - [ ] All 9 bare `except Exception` sites have structured logging with module, function, exception type, message
  - [ ] `grep -c "except Exception" backend/core/orchestrator.py` returns 0 bare catches (all narrowed or structured)
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: orchestrator.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/core/orchestrator.py
      2. For each match, verify the next line contains logger.error or logger.warning with f-string including type(e).__name__
      3. Run: grep -c "except Exception as e:\s*$" backend/core/orchestrator.py || echo "0" — assert count is 0 (no bare handlers without logging)
    Expected Result: Every except block has structured logging; zero bare exception handlers remain
    Failure Indicators: Any except Exception block without structured logging on next line
    Evidence: .sisyphus/evidence/task-15-exception-audit.txt

  Scenario: Backend tests still pass after changes
    Tool: Bash
    Preconditions: orchestrator.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output, no "failed"
    Expected Result: 528+ tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-15-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 16, 17, 18, 19)
  - Message: `fix(backend): structured error handling for critical-path modules`
  - Files: `backend/core/orchestrator.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 16. Audit Exception Handling in strategies/order_executor.py

  **What to do**:
  - Open `backend/strategies/order_executor.py` and locate all 4 bare `except Exception` sites
  - For each site, apply the same classification as Task 15:
    - Graceful degradation → structured log with `logger.error(f"[order_executor.{func_name}] {type(e).__name__}: {e}", exc_info=True)`
    - Re-raise → structured log before raise
    - Narrowable → narrow exception type + structured log
  - Every modified `except` block must include: module name (`order_executor`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite to confirm zero regressions

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change error handling semantics
  - Do NOT modify order execution logic or trading parameters
  - Do NOT remove any existing error handling

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic audit of exception handling in order execution critical path
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `systematic-debugging`: Not a debugging task

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 17, 18, 19)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start after Wave 2)

  **References**:

  **Pattern References**:
  - `backend/strategies/order_executor.py` — Full file; all 4 bare `except Exception` sites are targets

  **WHY Each Reference Matters**:
  - Order executor handles real money trades — unstructured exceptions here can hide critical order failures

  **Acceptance Criteria**:
  - [ ] All 4 bare `except Exception` sites have structured logging
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: order_executor.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/strategies/order_executor.py
      2. Verify each match has structured logging (logger.error/warning with type(e).__name__)
    Expected Result: All 4 sites have structured logging
    Failure Indicators: Any bare exception handler without structured logging
    Evidence: .sisyphus/evidence/task-16-exception-audit.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: order_executor.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
      2. Assert "passed" in output
    Expected Result: 528+ tests pass
    Failure Indicators: Any test failure
    Evidence: .sisyphus/evidence/task-16-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 15, 17, 18, 19)
  - Message: `fix(backend): structured error handling for critical-path modules`
  - Files: `backend/strategies/order_executor.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 17. Audit Exception Handling in core/risk_manager.py

  **What to do**:
  - Open `backend/core/risk_manager.py` and locate all 3 bare `except Exception` sites
  - Apply same classification: graceful degradation → structured log; re-raise → log + raise; narrowable → narrow + log
  - Every modified `except` block must include: module name (`risk_manager`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change risk management logic or risk limits
  - Do NOT change error handling semantics

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Only 3 exception sites — small, focused edit
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 18, 19)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start after Wave 2)

  **References**:

  **Pattern References**:
  - `backend/core/risk_manager.py` — Full file; all 3 bare `except Exception` sites

  **WHY Each Reference Matters**:
  - Risk manager is the safety net for position sizing — silent exceptions here could allow oversized positions

  **Acceptance Criteria**:
  - [ ] All 3 bare `except Exception` sites have structured logging
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: risk_manager.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/core/risk_manager.py
      2. Verify each match has structured logging
    Expected Result: All 3 sites have structured logging
    Failure Indicators: Any bare handler
    Evidence: .sisyphus/evidence/task-17-exception-audit.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: risk_manager.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
    Expected Result: 528+ tests pass
    Evidence: .sisyphus/evidence/task-17-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 15, 16, 18, 19)
  - Message: `fix(backend): structured error handling for critical-path modules`
  - Files: `backend/core/risk_manager.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 18. Audit Exception Handling in core/strategy_executor.py

  **What to do**:
  - Open `backend/core/strategy_executor.py` and locate all 4 bare `except Exception` sites
  - Apply same classification: graceful degradation → structured log; re-raise → log + raise; narrowable → narrow + log
  - Every modified `except` block must include: module name (`strategy_executor`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change strategy execution logic
  - Do NOT change error handling semantics

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Strategy executor coordinates all strategy runs — needs careful semantic analysis
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 17, 19)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start after Wave 2)

  **References**:

  **Pattern References**:
  - `backend/core/strategy_executor.py` — Full file; all 4 bare `except Exception` sites

  **WHY Each Reference Matters**:
  - Strategy executor dispatches to all trading strategies — unstructured exceptions could silently skip strategies

  **Acceptance Criteria**:
  - [ ] All 4 bare `except Exception` sites have structured logging
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: strategy_executor.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/core/strategy_executor.py
      2. Verify each match has structured logging
    Expected Result: All 4 sites have structured logging
    Failure Indicators: Any bare handler
    Evidence: .sisyphus/evidence/task-18-exception-audit.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: strategy_executor.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
    Expected Result: 528+ tests pass
    Evidence: .sisyphus/evidence/task-18-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 15, 16, 17, 19)
  - Message: `fix(backend): structured error handling for critical-path modules`
  - Files: `backend/core/strategy_executor.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 19. Audit Exception Handling in api/main.py

  **What to do**:
  - Open `backend/api/main.py` and locate all 10 bare `except Exception` sites
  - Apply same classification: graceful degradation → structured log; re-raise → log + raise; narrowable → narrow + log
  - For API endpoints specifically: ensure `except` blocks return proper HTTP status codes (500 for internal errors, 503 for upstream failures) with structured JSON error responses — do NOT change existing response structure, just ensure the logging is structured
  - Every modified `except` block must include: module name (`api.main`), function/endpoint name, `type(e).__name__`, `str(e)`
  - Run full backend test suite

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change API response contracts or status codes that already work correctly
  - Do NOT change error handling semantics
  - Do NOT modify the lifespan changes from Task 7 (those are separate)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 10 exception sites in the main API file — high-impact, needs careful analysis
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 15, 16, 17, 18)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: Task 7 (lifespan migration must be done first, both touch api/main.py)

  **References**:

  **Pattern References**:
  - `backend/api/main.py` — Full file; all 10 bare `except Exception` sites
  - `backend/api/main.py:263-344` — Lifespan section (modified by Task 7 — do NOT conflict)

  **WHY Each Reference Matters**:
  - API main is the user-facing surface — poor error responses make the dashboard unusable during failures

  **Acceptance Criteria**:
  - [ ] All 10 bare `except Exception` sites have structured logging
  - [ ] No API response contract changes (same status codes, same JSON shapes)
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: api/main.py modified (after Task 7 lifespan change)
    Steps:
      1. Run: grep -n "except Exception" backend/api/main.py
      2. Verify each match has structured logging (logger.error/warning with type(e).__name__)
      3. Verify no bare handlers remain without logging
    Expected Result: All 10 sites have structured logging
    Failure Indicators: Any bare exception handler without structured logging
    Evidence: .sisyphus/evidence/task-19-exception-audit.txt

  Scenario: API still responds correctly
    Tool: Bash (curl)
    Preconditions: Backend running locally
    Steps:
      1. Run: uvicorn backend.api.main:app --port 8099 &
      2. Wait 3s
      3. curl -s http://localhost:8099/api/health | python -m json.tool
      4. Assert response has "status" field
      5. Kill the background process
    Expected Result: Health endpoint returns valid JSON with status field
    Failure Indicators: Connection refused, non-JSON response, missing status field
    Evidence: .sisyphus/evidence/task-19-api-health.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: api/main.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
    Expected Result: 528+ tests pass
    Evidence: .sisyphus/evidence/task-19-tests-pass.txt
  ```

  **Commit**: YES (groups with Tasks 15, 16, 17, 18)
  - Message: `fix(backend): structured error handling for critical-path modules`
  - Files: `backend/api/main.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 20. Frontend Bundle Code Splitting — Lazy-load GlobeView and Heavy Chunks

  **What to do**:
  - Identify the heaviest chunks in the frontend build:
    - `GlobeView.tsx` contributes to a ~1.8MB chunk (includes globe/3D rendering library)
    - `index.js` is ~950KB (main bundle)
  - Add React.lazy + Suspense for `GlobeView.tsx`:
    - Replace direct import with `const GlobeView = React.lazy(() => import('./components/GlobeView'))`
    - Wrap usage in `<Suspense fallback={<div>Loading globe...</div>}>` (or a spinner component if one exists)
  - Check if other heavy components can also be lazy-loaded (e.g., chart libraries) — only split if the component is behind a route or tab (not always visible)
  - Optionally configure Vite manual chunks in `vite.config.ts` to separate vendor libraries (react, recharts, etc.) if not already done
  - Run `npm run build` and verify:
    - No single chunk exceeds 1MB (target: largest chunk < 500KB)
    - Build succeeds with no errors
    - Total bundle size is reduced

  **Must NOT do**:
  - Do NOT remove or refactor GlobeView functionality
  - Do NOT change component props or API
  - Do NOT install new packages — React.lazy and Suspense are built-in
  - Do NOT lazy-load components that are always visible on initial render (above the fold)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Frontend performance optimization involving React component loading patterns
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `frontend-ui-ux`: This is perf optimization, not UI design

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21, 22)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (independent of backend work)

  **References**:

  **Pattern References**:
  - `frontend/src/components/GlobeView.tsx` — The component to lazy-load
  - `frontend/vite.config.ts` — Build configuration for manual chunks
  - `frontend/src/App.tsx` or wherever GlobeView is imported — Import site to modify

  **External References**:
  - React docs: `React.lazy()` and `Suspense` — https://react.dev/reference/react/lazy

  **WHY Each Reference Matters**:
  - GlobeView is a 3D globe component likely using a heavy library (three.js, globe.gl, etc.) — lazy-loading it avoids penalizing initial page load
  - vite.config.ts may need manual chunk splitting to prevent vendor libraries from landing in the main bundle

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm run build` → succeeds with no errors
  - [ ] No single JS chunk exceeds 1MB in `frontend/dist/assets/`
  - [ ] GlobeView loads lazily (verified via build output showing separate chunk)
  - [ ] `cd frontend && npm test` → all tests still pass

  **QA Scenarios**:

  ```
  Scenario: Build succeeds and chunks are smaller
    Tool: Bash
    Preconditions: Frontend code modified
    Steps:
      1. Run: cd frontend && npm run build 2>&1 | tail -20
      2. Assert "built in" or similar success message
      3. Run: ls -lhS frontend/dist/assets/*.js | head -5
      4. Assert no file exceeds 1MB (1048576 bytes)
    Expected Result: Build passes; largest chunk < 1MB
    Failure Indicators: Build error; chunk > 1MB
    Evidence: .sisyphus/evidence/task-20-build-output.txt

  Scenario: GlobeView is in a separate chunk
    Tool: Bash (grep)
    Preconditions: Build completed
    Steps:
      1. Run: ls frontend/dist/assets/ | grep -i globe || echo "NO_GLOBE_CHUNK"
      2. If no dedicated chunk, check build output for chunk names containing the globe library
    Expected Result: A separate chunk file exists for globe-related code
    Failure Indicators: "NO_GLOBE_CHUNK" and globe code still in main bundle
    Evidence: .sisyphus/evidence/task-20-chunk-split.txt

  Scenario: Frontend tests still pass
    Tool: Bash
    Preconditions: Frontend code modified
    Steps:
      1. Run: cd frontend && npm test 2>&1 | tail -10
      2. Assert all tests pass
    Expected Result: All frontend tests pass (previously 5 were failing — those are fixed by Tasks 1-4)
    Failure Indicators: New test failures (not the pre-existing 5)
    Evidence: .sisyphus/evidence/task-20-tests-pass.txt
  ```

  **Commit**: YES
  - Message: `perf(frontend): code-split GlobeView and heavy chunks`
  - Files: `frontend/src/components/GlobeView.tsx` (or import site), `frontend/vite.config.ts`
  - Pre-commit: `cd frontend && npm run build`

- [ ] 21. Audit Exception Handling in data/polymarket_clob.py

  **What to do**:
  - Open `backend/data/polymarket_clob.py` and locate all 10 bare `except Exception` sites
  - Apply same classification as Tasks 15-19:
    - Graceful degradation → structured log: `logger.error(f"[polymarket_clob.{func_name}] {type(e).__name__}: {e}", exc_info=True)`
    - Re-raise → structured log before raise
    - Narrowable (e.g., `requests.RequestException`, `json.JSONDecodeError`, `ConnectionError`) → narrow type + structured log
  - Pay special attention to API call exception handling — network errors vs data parsing errors should be distinct exception types where possible
  - Every modified `except` block must include: module name (`polymarket_clob`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change error handling semantics
  - Do NOT modify API request logic or endpoints
  - Do NOT change retry behavior

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 10 exception sites in the primary market data integration — needs careful analysis
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20, 22)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start after Wave 3)

  **References**:

  **Pattern References**:
  - `backend/data/polymarket_clob.py` — Full file; all 10 bare `except Exception` sites
  - `backend/data/orderbook_ws.py` — For comparison: how the websocket module handles exceptions (reference pattern)

  **WHY Each Reference Matters**:
  - polymarket_clob is the primary data source for Polymarket markets — silent failures here mean the bot trades blind

  **Acceptance Criteria**:
  - [ ] All 10 bare `except Exception` sites have structured logging
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: polymarket_clob.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/data/polymarket_clob.py
      2. Verify each match has structured logging
    Expected Result: All 10 sites have structured logging
    Failure Indicators: Any bare handler
    Evidence: .sisyphus/evidence/task-21-exception-audit.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: polymarket_clob.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
    Expected Result: 528+ tests pass
    Evidence: .sisyphus/evidence/task-21-tests-pass.txt
  ```

  **Commit**: YES (groups with Task 22)
  - Message: `fix(backend): structured error handling for CLOB and settlement`
  - Files: `backend/data/polymarket_clob.py`
  - Pre-commit: `pytest --tb=short -q`

- [ ] 22. Audit Exception Handling in core/settlement_helpers.py

  **What to do**:
  - Open `backend/core/settlement_helpers.py` and locate all 12 bare `except Exception` sites
  - Apply same classification as Tasks 15-19:
    - Graceful degradation → structured log: `logger.error(f"[settlement_helpers.{func_name}] {type(e).__name__}: {e}", exc_info=True)`
    - Re-raise → structured log before raise
    - Narrowable → narrow type + structured log
  - Settlement is particularly sensitive — pay attention to whether exceptions during settlement resolution should halt the settlement process or allow partial completion
  - Every modified `except` block must include: module name (`settlement_helpers`), function name, `type(e).__name__`, `str(e)`
  - Run full backend test suite

  **Must NOT do**:
  - Do NOT add try/except where none existed
  - Do NOT change settlement logic or resolution outcomes
  - Do NOT change error handling semantics (if partial settlement was allowed before, keep it)
  - Do NOT modify payout calculations

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 12 exception sites in settlement — the highest count; settlement correctness is critical for financial accuracy
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20, 21)
  - **Blocks**: F1, F2, F3, F4
  - **Blocked By**: None (can start after Wave 3)

  **References**:

  **Pattern References**:
  - `backend/core/settlement_helpers.py` — Full file; all 12 bare `except Exception` sites

  **WHY Each Reference Matters**:
  - Settlement helpers resolve trade outcomes and calculate payouts — silent exceptions here could mean trades are never settled or incorrectly settled

  **Acceptance Criteria**:
  - [ ] All 12 bare `except Exception` sites have structured logging
  - [ ] `pytest backend/tests/ -q --tb=short` → 528+ pass, 0 fail

  **QA Scenarios**:

  ```
  Scenario: Verify all exception sites have structured logging
    Tool: Bash (grep)
    Preconditions: settlement_helpers.py modified
    Steps:
      1. Run: grep -n "except Exception" backend/core/settlement_helpers.py
      2. Verify each match has structured logging
    Expected Result: All 12 sites have structured logging
    Failure Indicators: Any bare handler
    Evidence: .sisyphus/evidence/task-22-exception-audit.txt

  Scenario: Backend tests still pass
    Tool: Bash
    Preconditions: settlement_helpers.py modified
    Steps:
      1. Run: pytest backend/tests/ -q --tb=short 2>&1 | tail -5
    Expected Result: 528+ tests pass
    Evidence: .sisyphus/evidence/task-22-tests-pass.txt
  ```

  **Commit**: YES (groups with Task 21)
  - Message: `fix(backend): structured error handling for CLOB and settlement`
  - Files: `backend/core/settlement_helpers.py`
  - Pre-commit: `pytest --tb=short -q`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `cd frontend && npm run build && npm test`. Run `pytest --tb=short -q` from project root. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (frontend tests all pass together, backend tests all pass together). Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git diff`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Wave | Commit | Message | Files | Pre-commit |
|------|--------|---------|-------|------------|
| 1 | 1 | `fix(frontend): fix vitest config and broken test mocks` | vitest.config.ts, 3 test files | `cd frontend && npm test` |
| 1 | 2 | `fix(backend): resolve deprecation warnings in config, models, api, core` | config.py, database.py, main.py, retry.py, errors.py, sentiment_analyzer.py | `pytest --tb=short -q` |
| 2 | 3 | `docs: rewrite ARCHITECTURE.md, IMPLEMENTATION_GAPS.md, README.md to match reality` | ARCHITECTURE.md, IMPLEMENTATION_GAPS.md, README.md | — |
| 2 | 4 | `fix(backend): de-scope email notification, fix market maker inventory, fix CLOB websocket` | notification_router.py, market_maker.py, ws_client.py or orderbook_ws.py | `pytest --tb=short -q` |
| 3 | 5 | `fix(backend): structured error handling for critical-path modules` | orchestrator.py, order_executor.py, risk_manager.py, strategy_executor.py, main.py | `pytest --tb=short -q` |
| 4 | 6 | `perf(frontend): code-split GlobeView and heavy chunks` | vite.config.ts or component lazy imports | `cd frontend && npm run build` |
| 4 | 7 | `fix(backend): structured error handling for CLOB and settlement` | polymarket_clob.py, settlement_helpers.py | `pytest --tb=short -q` |

---

## Success Criteria

### Verification Commands
```bash
cd frontend && npm test        # Expected: all pass, 0 failures
cd frontend && npm run build   # Expected: pass, no chunk >500KB
pytest --tb=short -q           # Expected: 528+ pass, 0 fail, <100 warnings
grep -rn "from sqlalchemy.ext.declarative import" backend/  # Expected: 0 matches
grep -rn "@app.on_event" backend/                           # Expected: 0 matches
grep -rn "asyncio.iscoroutinefunction" backend/             # Expected: 0 matches
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Frontend: 0 test failures
- [ ] Backend: 528+ tests passing
- [ ] Backend: <100 warnings (down from 69,348)
- [ ] Documentation: ARCHITECTURE.md, README.md, IMPLEMENTATION_GAPS.md accurate
- [ ] All 4 final verification agents approve
