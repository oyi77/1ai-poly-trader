# ADR-003: Trade Attempt Observability Ledger

**Status:** Accepted  
**Date:** 2026-04-27

## Context

Operators need to answer: "Why did this trade happen?" and "Why did this trade not happen?" Existing observability was fragmented across `DecisionLog`, `ActivityLog`, `Signal.reasoning`, runtime logs, and dashboard trade history. That was insufficient because logs are not durable/queryable enough for the dashboard, and `Trade` only represents executions, not rejected attempts.

The system must preserve historical trade data for re-learning and must not reset or rewrite the `Trade` ledger to explain current behavior.

## Decision

Add a dedicated `trade_attempts` ledger with one row per strategy execution attempt that reaches `backend.core.strategy_executor.execute_decision()`.

Each attempt records:

- identity: `attempt_id`, `correlation_id`, timestamps,
- context: strategy, mode, market, platform, direction,
- lifecycle: status, phase, reason code, human reason,
- risk/sizing data: bankroll, exposure, requested size, adjusted size, confidence, edge,
- outcome links: `trade_id`, `order_id`, latency,
- JSON context: decision data, signal/AI reasoning, evaluated factors.

The dashboard **Control Room** tab and `/api/v1/trade-attempts*` endpoints read from this ledger. `Trade` remains the source of executed-position history; `DecisionLog` remains useful for strategy/AI decision history; `TradeAttempt` is the execution observability layer between them.

## Alternatives Considered

1. **Parse scheduler and bot logs.** Rejected because logs rotate, are not schema-stable, and cannot reliably power filters, counts, or UI explanations.
2. **Reuse `DecisionLog` only.** Rejected because it does not consistently capture risk validation, sizing, broker rejection, duplicate-position checks, or execution latency.
3. **Store only failed attempts.** Rejected because operators also need successful baselines and execution-rate metrics.
4. **Full immutable event-sourcing immediately.** Deferred. A one-row-per-attempt ledger is smaller, lower-risk for the trading hot path, and still provides durable production visibility. A future event stream can build on `correlation_id`.

## Consequences

- Operators can see live blockers such as drawdown breaker, max exposure, minimum order size, duplicate position, and missing token ID directly in the dashboard.
- Attempt recording adds lightweight DB writes on the serialized execution path. This is acceptable because execution is already DB-backed and serialized for bankroll/exposure correctness.
- The first slice focuses on standard `strategy_executor` attempts. HFT-specific execution can be instrumented later using the same table and status taxonomy.
- The table is append/update operational telemetry, not financial accounting. Financial correctness still comes from `Trade`, `BotState`, and reconciliation rules in ADR-002.
