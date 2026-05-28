# Open Questions

This file tracks unresolved questions, decisions deferred to the user, and items needing clarification before or during execution.

## Phase 1: Production Readiness - 2026-04-07

### Migration Strategy for Existing Databases
- [ ] **Question:** How should existing `tradingbot.db` files be migrated to Alembic? — Current database has `clob_order_id` column added via `ensure_schema()` (line 357 of `database.py`). Initial migration needs to handle both fresh and existing databases.
  - **Impact:** Affects Step 1.6 implementation
  - **Options:** (1) `alembic stamp head` for existing DBs, (2) Manual migration script, (3) Documented backup/recreate procedure
  - **Default if unresolved:** Use `alembic stamp head` approach with documentation

### Prometheus Metrics Storage Retention
- [ ] **Question:** What retention period for Prometheus metrics in production? — Time-series data storage grows continuously.
  - **Impact:** Affects Step 3.7 Prometheus configuration
  - **Options:** (1) 15 days default, (2) 30 days for analysis, (3) 90 days for seasonal patterns
  - **Default if unresolved:** 15 days (Prometheus default)

### Grafana Dashboard Access Control
- [ ] **Question:** Should Grafana be secured with authentication in production deployments?
  - **Impact:** Affects Step 3.6 docker-compose.yml configuration
  - **Options:** (1) Password auth (admin/admin), (2) OAuth via GitHub/Google, (3) Proxy behind existing auth
  - **Default if unresolved:** Password auth with environment variable override

### Test Coverage Exemptions
- [ ] **Question:** Are any modules exempt from the 80% coverage requirement?
  - **Impact:** Affects Step 4.9 CI configuration
  - **Options:** (1) No exemptions, (2) UI/test utilities exempt, (3) Specific modules listed
  - **Default if unresolved:** No exemptions for `backend/`; frontend tracked separately

### CI Pipeline Resource Limits
- [ ] **Question:** Should CI enforce time limits for test execution?
  - **Impact:** Affects Step 4.9 `.github/workflows/ci.yml` update
  - **Options:** (1) 10 minute timeout, (2) 20 minute timeout, (3) No limit
  - **Default if unresolved:** 20 minute timeout

---

## perf-docs-consensus (Iteration 2) - 2026-05-27

- [ ] Does `fetch_resolution_for_trade()` in settlement.py make additional DB queries internally? — If so, the batch fix impact on total query count is smaller than the Trade lookup alone. Addressed by Phase 0 baseline measurement distinguishing DB queries from external API calls.
- [ ] Should `_chunked_ids()` utility be placed in `backend/db/utils.py` or `backend/utils/`? — Used by settlement and potentially signals batch query. Needs a shared location.
- [ ] Activity source `MIN_POLL_INTERVAL` value (5s) — Is 5s sufficient for all platforms? Some platforms (e.g., Hyperliquid) may need faster polling. Consider per-source override.
- [ ] Calibration Brier score SQL — does `actual_outcome` column already store 1.0/0.0, or does it need a CASE mapping from string "win"/"loss"? Must verify before SQL migration.

---

## ralplan-arb-consolidation v2 - 2026-05-28

- [ ] Should `ArbOpportunityScanner._normalize_*` helpers be extracted to shared module? -- New strategy needs similar normalization for `MarketInfo` objects from providers.
- [ ] Max opportunities per cycle (10) -- too aggressive or conservative? -- Affects rate limiting and API load across multiple venues.
- [ ] Per-provider AGI health visibility -- `unified_pm_arb` evaluated as one strategy; do we need per-provider logging for debugging when one venue underperforms?

---

**Instructions:** When a question is resolved, remove it from this file and document the decision in the appropriate ADR or implementation plan.
