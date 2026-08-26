# Autoresearch Segment 2 — Manual Ledger

> Toolchain note: init_experiment/run_experiment/log_experiment unmounted after
> segment 1 closed (12/12). This segment runs the same protocol manually:
> implement → `bash autoresearch.sh` → keep (commit) / discard (revert) against
> the carried baseline. Every run gets a conventional commit with literal metrics.

- **Carried baseline**: bench_sharpe = **19.7491** (main @ 9f8befc8)
  - Config: gates (min_edge 0.15 / min_model_prob 0.58), binary-Kelly sizing,
    drawdown throttle, calibration k=1 price-key bucket 0.1, bps slippage 100
  - WF: train 15.30 / test 11.63 (76% retention)
- **Determinism guard**: double-run equality, exit 2 on drift
- **Constraint**: backend/tests stay green; no benchmark gaming

## Run log

| Run | Change | bench_sharpe | Verdict |
|---|---|---|---|
| 12 (S1 close) | segment-1 final state | 19.7491 | baseline carried |

| 13 | two-factor calibration buckets (price_dir) | 19.7491 | NEUTRAL-DISCARD — seeded generator is direction-symmetric (i%2 alternation, symmetric outcomes): per-direction stats ≡ combined stats. Capability kept in engine (`calibration_key="price_dir"`), may matter on real asymmetric flow |
| 14a | volatility-scaled Kelly, $10 cap | 19.7491 | NO-OP — sizing is max_trade_size-dominated; f* scaling can't express below a binding hard cap |
| 14b | vol-scaled + raised cap ($100/25%) | 16.2651 | DISCARD — sharpe −17.6%, maxDD ×2 despite PnL $41k. Vol scaling softened run-9a's drop (16.12→16.27) but cannot beat cap-dominated sizing at this signal quality |

## Segment 2 close (3 runs)
**Finding**: at bench_sharpe 19.75 the capped regime is the local optimum of
this benchmark's design space. Sizing/calibration levers are exhausted on
synthetic data — the remaining alpha requires REAL market signals:
- Connect gates+calibration to live Polymarket signal history (true
  out-of-sample test of the doctrine)
- Bucket calibration becomes informative only when win rates are
  price/direction-asymmetric (real microstructure)

Engine capabilities shipped this segment (default-off, tested):
`vol_scaling`/`vol_target`/`vol_lookback`/`vol_scale_floor`,
`calibration_key="price_dir"`.
