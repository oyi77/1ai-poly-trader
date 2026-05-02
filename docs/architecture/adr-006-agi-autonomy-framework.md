# ADR-006: AGI Autonomy Framework

**Status:** Accepted  
**Date:** 2026-04-30

## Context

PolyEdge is evolving from Level 3 Agentic AI (executes preset strategies with bounded parameter tuning) toward Level 5 TRUE-AGI (composes new strategies, detects market regimes, learns persistently, self-debugs, and autonomously switches goals). This expansion introduces autonomous actions that could affect capital, system stability, and operational costs.

Existing ADRs establish hard boundaries:
- ADR-002 defines live equity as derived from CLOB USDC cash + Polymarket open-position value — not local ledger P&L
- ADR-004 mandates that autonomous sizing proposals must pass through deterministic RiskManager gates
- ADR-005 enforces static risk profiles that learning cannot bypass

The AGI system needs clear, enforceable boundaries on what it CAN and CANNOT do autonomously.

## Decision

Define four autonomy boundaries for the AGI system:

### 1. Strategy Composition Bounded by Risk Profiles
Autonomous strategy composition (combining signal sources, filters, position sizers, risk rules, exit rules into StrategyBlocks) is permitted, but every composed strategy MUST validate through the existing RiskManager pipeline. The risk profiles defined in ADR-005 (safe, normal, aggressive, extreme) remain the non-bypassable authority. No composed strategy may exceed the position size, drawdown, or exposure limits of the active risk profile.

### 2. Code Generation Requires Shadow → Paper → Live Promotion
LLM-generated strategy code (Python modules) MUST follow the existing promotion pipeline:
- DRAFT: Code generated but not executed
- SHADOW: Paper-traded with simulated bankroll, no real orders
- PAPER: Paper-traded with statistical validation (minimum trades, Sharpe ratio, max drawdown)
- LIVE_PROMOTED: Live trading with real capital, only after passing statistical gates
- LIVE_FAILED: Demoted from live after performance degradation
- RETIRED: Permanently removed from rotation

No generated strategy may skip stages or bypass the promotion manager. Human approval is required for LIVE_PROMOTED status **by default**. The `AGI_AUTO_PROMOTE` environment flag (default `false`) can opt‑in to fully automatic paper→live promotion when the system must operate unsupervised; this override remains bound by the same statistical promotion thresholds.

### 3. LLM Spending Has Hard Caps
Autonomous LLM operations (strategy generation, market analysis, self-debugging) are budgeted per cycle:
- Maximum $10/day for AGI operations
- Per-operation cap tracked and enforced before each LLM call
- Budget resets daily; overspend triggers fallback to cached analysis
- Spending is logged in DecisionAuditEntry for human review

### 4. Experiment Isolation Prevents Production Access
Sandboxed experiments (strategy testing, code generation, causal reasoning) MUST NOT access:
- Production database (separate experiment DB)
- Real wallet or API keys (simulated credentials only)
- Live order execution (paper-trading only)
- Production BotState (isolated experiment state)

Experiments run in ExperimentStatus.DRAFT or SHADOW status cannot modify production state.

## Alternatives Considered

1. **Unlimited AGI autonomy with post-hoc review.** Rejected because capital risk requires pre-validation, not post-hoc auditing. A single unbounded autonomous trade could exceed risk limits.

2. **Human approval for every AGI action.** Rejected because it defeats the purpose of autonomous operation. The system would be no better than manual trading with extra steps.

3. **Soft budget limits with alerts.** Rejected because LLM API costs can escalate rapidly. Hard caps prevent runaway spending that could exceed the trading profit.

4. **Shared database with row-level security.** Rejected because SQL-level isolation is fragile and a single misconfigured query could corrupt production state. Separate databases provide true isolation.

## Consequences

- AGI can compose and test strategies autonomously within risk bounds
- All autonomous decisions are auditable via DecisionAuditEntry (regime, goal, strategy, signal, reasoning, outcome)
- Generated strategies follow the same promotion pipeline as human-created strategies
- LLM costs are predictable and bounded
- Production capital and data are protected from experiment failures
- Human operators retain final authority over live trading via the promotion gate **(override possible only via explicit `AGI_AUTO_PROMOTE=true` opt-in)**
- Future adaptive sizing can be layered inside existing caps without changing the risk authority boundary (consistent with ADR-005)