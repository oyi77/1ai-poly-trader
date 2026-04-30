# ADR-005: Static Risk Profiles and Learning Boundary

**Status:** Accepted  
**Date:** 2026-04-29

## Context

PolyEdge now has self-improvement jobs, proposal execution, online learning tables, and strategy outcome feedback. That creates an operational requirement: learning may improve calibration, allocation, health checks, and proposal quality, but it must not rewrite the hard controls that keep capital at risk bounded.

The Admin Risk tab also needs operator-selectable modes such as safe, normal, aggressive, and extreme. Those modes must be real runtime guardrails, not passive UI labels or non-authoritative database rows.

## Decision

Use **static operator-selected risk profiles** as preset overlays for the same `backend.config.settings` fields that `RiskManager` already reads.

- Profiles are fixed in `backend/core/risk_profiles.py`.
- Applying a profile updates runtime settings such as `KELLY_FRACTION`, `MIN_EDGE_THRESHOLD`, `MAX_TRADE_SIZE`, drawdown limits, exposure caps, and slippage tolerance.
- `RiskManager.validate_trade()` remains the deterministic execution authority.
- Online learning records settlement outcomes through `OnlineLearner` and `StrategyOutcome`, but learning code does not modify profile definitions or bypass risk validation.
- The active profile name is persisted best-effort to `.env` as `RISK_PROFILE` alongside the applied numeric settings.

## Alternatives Considered

1. **User-authored database risk profiles.** Rejected for the first production slice because fixed profiles satisfy the current operator need without schema changes or governance complexity.
2. **Dynamic Kelly/bandit profile switching.** Deferred because adaptive sizing should be trained in shadow mode and still operate inside deterministic caps.
3. **Constrained RL / CBF action shield.** Deferred because it adds solver dependencies and numerical failure modes; static profiles deliver immediate safety without new infrastructure.
4. **Frontend-only profiles.** Rejected because UI-only presets would be fake; profiles must mutate backend settings used by `RiskManager`.

## Consequences

- Operators can switch between safe, normal, aggressive, and extreme risk presets from Admin.
- Manual granular risk edits and preset application now target authoritative runtime settings.
- Learning becomes truthful: settled trades persist `StrategyOutcome` rows for calibration, Thompson sampling, health monitoring, and safe parameter tuning.
- Profile definitions require code review to change, which is intentional: learning and UI users cannot silently expand hard limits.
- Future adaptive sizing can be layered inside these caps without changing the risk authority boundary.
