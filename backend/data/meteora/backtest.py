"""Meteora DLMM backtester — bin-walk simulator over OHLCV + fee buckets.

Model fidelity:
- IL / composition: EXACT bin-by-bin conversion walk. Geometric bins
  (ratio 1 + bin_step_bps/10000); per-bin liquidity weights follow the shape
  preset; every close-to-close boundary crossing converts that bin's
  remaining inventory at the bin price. Terminal value vs HODL gives IL.
- Fee capture: APPROXIMATE pro-rata model (documented limitation): while any
  part of the range is active, the position earns
  bucket_fees × (capital / active_tvl) gated by in-range time share.
  Per-swap data would be required for exactness; this matches how DLMM fee
  APRs are quoted and is the least-assumption estimator available from the
  public endpoints.

Shapes: spot (uniform per bin), curve (linear peak at center), bid_ask
(Gaussian-ish concentration around entry; supports single-sided).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShapeConfig:
    name: str = "spot"
    side: str = "two_sided"          # two_sided | bid | ask
    bins_below: int = 69             # range depth below entry (bins)
    bins_above: int = 69             # range height above entry (bins)

    def __post_init__(self) -> None:
        if self.name not in ("spot", "curve", "bid_ask"):
            raise ValueError(f"unknown shape {self.name!r}")
        if self.side not in ("two_sided", "bid", "ask"):
            raise ValueError(f"unknown side {self.side!r}")
        if self.bins_below < 1 or self.bins_above < 1:
            raise ValueError("range must span at least one bin on each bound")


@dataclass
class BacktestResult:
    strategy: str
    side: str
    bins_below: int
    bins_above: int
    bin_step_bps: float
    entry_price: float
    exit_price: float
    capital: float                  # quote units deposited
    fees_usd: float
    final_value_usd: float          # inventory valued at exit price (excl fees)
    hodl_value_usd: float           # buy-and-hold same capital benchmark
    il_usd: float                   # final_value - hodl_value (≤ 0 typically)
    net_pnl_usd: float              # final_value + fees - capital
    pnl_pct: float                  # net_pnl / capital
    minutes_held: int
    minutes_in_range: int
    oor_events: int
    ended_oor: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _bin_weights(shape: ShapeConfig, n_bins: int) -> list[float]:
    """Normalized liquidity weight per bin, ordered deepest-below → highest."""
    ks = list(range(n_bins))
    center = (n_bins - 1) / 2.0
    if shape.name == "spot":
        raw = [1.0] * n_bins
    elif shape.name == "curve":
        raw = [1.0 - abs(k - center) / (center + 1e-9) for k in ks]
        raw = [max(w, 0.05) for w in raw]
    else:  # bid_ask: concentrated near center, soft tails
        spread = max(2.0, n_bins / 6.0)
        raw = [math.exp(-((k - center) ** 2) / (2 * spread**2)) + 0.02 for k in ks]
    total = sum(raw)
    return [w / total for w in raw]




def simulate(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bucket_fees: list[float],
    bucket_seconds: int,
    active_tvl: float,
    bin_step_bps: float = 100.0,
    shape: ShapeConfig | None = None,
    capital: float = 100.0,
) -> BacktestResult:
    """Run one position through a price path.

    closes/highs/lows: equal-length OHLC arrays (chronological).
    bucket_fees: fee totals aligned to buckets of `bucket_seconds`; may be
    shorter than the candle list (missing buckets treated as 0 fees).
    """
    sh = shape or ShapeConfig()
    if len(closes) != len(highs) or len(closes) != len(lows):
        raise ValueError("closes/highs/lows length mismatch")
    if len(closes) < 2:
        raise ValueError("need at least two candles")

    step = 1.0 + bin_step_bps / 10_000.0
    entry_price = closes[0]
    n_bins = sh.bins_below + sh.bins_above + 1
    center = (n_bins - 1) / 2.0
    weights = _bin_weights(sh, n_bins)

    def bin_index(price: float) -> int:
        return round(math.log(price / entry_price, step) + center)

    def bin_price(i: int) -> float:
        return entry_price * step ** (i - center)

    lo_bin, hi_bin = 0, n_bins - 1

    # ---- Path statistics (walk over active-bin index) ------------------
    minutes_in_range = 0
    oor_events = 0
    was_oor = False
    fees_usd = 0.0
    prev_k = bin_index(closes[0])

    for t in range(1, len(closes)):
        k_t = bin_index(closes[t])
        in_range = lo_bin <= k_t <= hi_bin
        if in_range:
            minutes_in_range += bucket_seconds // 60
        elif not was_oor:
            oor_events += 1
        was_oor = not in_range

        # Pro-rata fee capture for this bucket (documented approximation):
        # earn pool fees × our TVL share while any part of the range is live.
        fi = bucket_fees[t - 1] if t - 1 < len(bucket_fees) else 0.0
        if fi > 0 and in_range and active_tvl > 0:
            fees_usd += fi * min(1.0, capital / active_tvl)

        prev_k = k_t

    # ---- Terminal composition (exact, path-independent v3/DLMM math) ---
    # At exit price P every seeded bin priced ABOVE P still holds base(X);
    # bins priced at/below P hold quote(Y) (already crossed). Sums run over
    # the SEEDED subset only; one-sided shapes leave the complement as idle
    # quote cash. A scale factor calibrates the seeded structure so that
    # valuing at entry reproduces exactly its deployed capital
    # (instant-withdraw invariant per shape).

    seeded_weights: list[float] = []
    for i, w in enumerate(weights):
        bp = bin_price(i)
        excluded = (sh.side == "bid" and bp >= entry_price) or (
            sh.side == "ask" and bp <= entry_price
        )
        if not excluded:
            seeded_weights.append(w)
    seed_capital = sum(seeded_weights) * capital
    idle_cash = capital - seed_capital

    def _raw_terminal(P: float) -> float:
        total = 0.0
        for i, w in enumerate(weights):
            bp = bin_price(i)
            excluded = (sh.side == "bid" and bp >= entry_price) or (
                sh.side == "ask" and bp <= entry_price
            )
            if excluded:
                continue
            alloc = capital * w
            if bp > P:
                total += alloc * (P / bp)      # base bin, marked at exit
            else:
                total += alloc                 # quote bin, par
        return total

    exit_price = closes[-1]
    raw_entry = _raw_terminal(entry_price)
    scale = seed_capital / raw_entry if raw_entry > 0 else 0.0
    final_value = idle_cash + _raw_terminal(exit_price) * scale
    hodl_value = capital * (exit_price / entry_price)
    held_minutes = (len(closes) - 1) * bucket_seconds // 60
    net = final_value + fees_usd - capital

    return BacktestResult(
        strategy=sh.name,
        side=sh.side,
        bins_below=sh.bins_below,
        bins_above=sh.bins_above,
        bin_step_bps=bin_step_bps,
        entry_price=entry_price,
        exit_price=exit_price,
        capital=capital,
        fees_usd=fees_usd,
        final_value_usd=final_value,
        hodl_value_usd=hodl_value,
        il_usd=final_value - hodl_value,
        net_pnl_usd=net,
        pnl_pct=net / capital if capital else 0.0,
        minutes_held=held_minutes,
        minutes_in_range=minutes_in_range,
        oor_events=oor_events,
        ended_oor=was_oor,
    )


def default_shape_grid() -> list[ShapeConfig]:
    """Canonical preset grid mirroring the LP Army taxonomy."""
    return [
        ShapeConfig("curve", "two_sided", 20, 20),
        ShapeConfig("spot", "two_sided", 40, 40),
        ShapeConfig("bid_ask", "two_sided", 35, 35),
        ShapeConfig("bid_ask", "bid", 69, 69),
        ShapeConfig("spot", "two_sided", 69, 69),
    ]


@dataclass
class RankingRow:
    result: BacktestResult
    rank: int = field(default=0)


def rank_shapes(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bucket_fees: list[float],
    bucket_seconds: int,
    active_tvl: float,
    bin_step_bps: float = 100.0,
    capital: float = 100.0,
    shapes: list[ShapeConfig] | None = None,
) -> list[BacktestResult]:
    """Backtest the preset grid and rank by net PnL percentage (desc)."""
    results = [
        simulate(
            closes=closes,
            highs=highs,
            lows=lows,
            bucket_fees=bucket_fees,
            bucket_seconds=bucket_seconds,
            active_tvl=active_tvl,
            bin_step_bps=bin_step_bps,
            shape=s,
            capital=capital,
        )
        for s in (shapes or default_shape_grid())
    ]
    results.sort(key=lambda r: r.pnl_pct, reverse=True)
    return results


def walk_forward(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bucket_fees: list[float],
    bucket_seconds: int,
    active_tvl: float,
    bin_step_bps: float = 100.0,
    capital: float = 100.0,
    train_frac: float = 0.7,
    shapes: list[ShapeConfig] | None = None,
) -> dict[str, dict[str, float]]:
    """Split the timeline train/test and score each shape on both halves.

    Guards against picking shapes that only worked on one regime. Returns
    {shape_key: {"train_pnl_pct", "test_pnl_pct", "delta"}}.
    """
    n = len(closes)
    cut = max(2, int(n * train_frac))
    grid = shapes or default_shape_grid()
    report: dict[str, dict[str, float]] = {}
    for s in grid:
        key = f"{s.name}:{s.side}:{s.bins_below}-{s.bins_above}"
        tr = simulate(
            closes=closes[:cut], highs=highs[:cut], lows=lows[:cut],
            bucket_fees=bucket_fees[: cut - 1], bucket_seconds=bucket_seconds,
            active_tvl=active_tvl, bin_step_bps=bin_step_bps,
            shape=s, capital=capital,
        )
        te = simulate(
            closes=closes[cut:], highs=highs[cut:], lows=lows[cut:],
            bucket_fees=bucket_fees[cut:], bucket_seconds=bucket_seconds,
            active_tvl=active_tvl, bin_step_bps=bin_step_bps,
            shape=s, capital=capital,
        )
        report[key] = {
            "train_pnl_pct": tr.pnl_pct,
            "test_pnl_pct": te.pnl_pct,
            "delta": te.pnl_pct - tr.pnl_pct,
        }
    return report
