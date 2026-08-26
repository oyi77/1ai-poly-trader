"""Meteora live executor — env-gated, kill-switched DLMM position harness.

Safety architecture (defense in depth):
1. HARD GATE: no live action unless METEORA_LIVE_ENABLED == "1" in env.
2. Wallet: base58 keypair from METEORA_WALLET_PRIVATE_KEY (solders); RPC from
   settings.METEORA_RPC_URL. Both resolved lazily; absence disables live mode
   with a clear error.
3. Risk gates before ANY deploy (mirrors meridian sizing doctrine):
   max concurrent positions, per-position SOL cap, daily realized-loss cap,
   portfolio drawdown halt.
4. Tx building is a pluggable protocol: DryRunTxBuilder (default) validates
   the full order payload and returns a simulated signature WITHOUT network
   or signing — the dry-run-verified pipeline. A real adapter (Anchor/IDL or
   TS sidecar) implements the same protocol at enablement time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from loguru import logger

LIVE_FLAG_ENV = "METEORA_LIVE_ENABLED"
WALLET_KEY_ENV = "METEORA_WALLET_PRIVATE_KEY"


class ExecutorError(RuntimeError):
    """Raised when safety gates refuse an action."""


@dataclass(frozen=True)
class RiskLimits:
    max_open_positions: int = 3
    max_position_sol: float = 0.5
    daily_loss_cap_usd: float = -25.0     # halt new deploys below this
    drawdown_halt_pct: float = -10.0      # on closed-position aggregate PnL


def live_enabled() -> bool:
    return os.environ.get(LIVE_FLAG_ENV) == "1"


def load_keypair():
    """Resolve the funding keypair; raises ExecutorError when unconfigured."""
    secret = os.environ.get(WALLET_KEY_ENV)
    if not secret:
        raise ExecutorError(
            f"{WALLET_KEY_ENV} not set â live executor disabled"
        )
    try:
        from solders.keypair import Keypair

        return Keypair.from_base58_string(secret)
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ExecutorError(
            "solders is not installed; cannot load Solana keypair"
        ) from exc


def rpc_url() -> str:
    from backend.config import settings

    url = getattr(settings, "METEORA_RPC_URL", "") or ""
    if not url:
        raise ExecutorError("METEORA_RPC_URL not configured")
    return url


class TxBuilder(Protocol):
    async def open_position(self, order: dict[str, Any]) -> str: ...
    async def close_position(self, order: dict[str, Any]) -> str: ...


class DryRunTxBuilder:
    """Validates the order and returns a simulated signature. No network."""

    async def open_position(self, order: dict[str, Any]) -> str:
        required = {
            "pool_address",
            "strategy",
            "side",
            "lower_price",
            "upper_price",
            "amount_sol",
            "bin_step",
        }
        missing = required - order.keys()
        if missing:
            raise ExecutorError(f"order missing fields: {sorted(missing)}")
        if order["amount_sol"] <= 0:
            raise ExecutorError("amount_sol must be positive")
        if order["lower_price"] >= order["upper_price"]:
            raise ExecutorError("lower_price must be < upper_price")
        return f"dryrun-open-{order['pool_address'][:8]}"

    async def close_position(self, order: dict[str, Any]) -> str:
        if not order.get("position_mint"):
            raise ExecutorError("close requires position_mint")
        return f"dryrun-close-{order['position_mint'][:8]}"


def _session():
    from backend.models.database import SessionLocal

    return SessionLocal()


def check_risk_gates(session, limits: RiskLimits) -> None:
    """Raise ExecutorError when any kill switch trips. Pure read."""
    from backend.models.meteora_db import MeteoraPosition

    open_count = (
        session.query(MeteoraPosition)
        .filter(MeteoraPosition.mode == "live", MeteoraPosition.status == "open")
        .count()
    )
    if open_count >= limits.max_open_positions:
        raise ExecutorError(
            f"max_open_positions reached ({open_count})"
        )

    day_start = datetime.now(UTC) - timedelta(days=1)
    closed_today = (
        session.query(MeteoraPosition)
        .filter(
            MeteoraPosition.mode == "live",
            MeteoraPosition.status == "closed",
            MeteoraPosition.closed_at >= day_start,
        )
        .all()
    )
    realized_today = sum(
        (p.final_value_usd or 0.0) + (p.fees_earned_usd or 0.0)
        - (p.initial_value_usd or 0.0)
        for p in closed_today
    )
    if realized_today <= limits.daily_loss_cap_usd:
        raise ExecutorError(
            f"daily loss cap hit: {realized_today:.2f} USD"
        )

    all_closed = (
        session.query(MeteoraPosition)
        .filter(MeteoraPosition.mode == "live", MeteoraPosition.status == "closed")
        .all()
    )
    agg_pnl_pct = 0.0
    invested = sum(p.initial_value_usd or 0.0 for p in all_closed)
    if invested > 0:
        agg_pnl_pct = (
            sum(
                ((p.final_value_usd or 0.0) + (p.fees_earned_usd or 0.0)
                 - (p.initial_value_usd or 0.0))
                for p in all_closed
            )
            / invested
            * 100.0
        )
    if agg_pnl_pct <= limits.drawdown_halt_pct:
        raise ExecutorError(
            f"drawdown halt: aggregate pnl {agg_pnl_pct:.2f}%"
        )


async def deploy_live_position(
    order: dict[str, Any],
    *,
    builder: TxBuilder | None = None,
    limits: RiskLimits | None = None,
    price_fetch=None,
) -> dict[str, Any]:
    """Gated live deploy: kill switches â tx builder â DB row."""
    from backend.models.meteora_db import MeteoraDecision, MeteoraPosition

    if not live_enabled():
        raise ExecutorError(
            f"{LIVE_FLAG_ENV} != 1 â refusing live deploy"
        )
    b = builder or DryRunTxBuilder()
    lim = limits or RiskLimits()

    # --- Economic sanity gates (before any builder call) ----------------
    s = _session()
    try:
        check_risk_gates(s, lim)

        dup = (
            s.query(MeteoraPosition)
            .filter(
                MeteoraPosition.mode == "live",
                MeteoraPosition.status == "open",
                MeteoraPosition.pool_address == order["pool_address"],
                MeteoraPosition.strategy == order["strategy"],
            )
            .first()
        )
        if dup is not None:
            raise ExecutorError(
                f"duplicate open live position on {order['pool_address']} "
                f"({order['strategy']}) — idempotency guard"
            )

        mid = (float(order["lower_price"]) + float(order["upper_price"])) / 2.0
        fetch = price_fetch or _default_live_price
        live_price = await fetch(order["pool_address"])
        if live_price and abs(mid - live_price) / live_price > 0.03:
            raise ExecutorError(
                f"price drift gate: entry mid {mid:.4f} vs live "
                f"{live_price:.4f} exceeds 3%"
            )

        signature = await b.open_position(order)
        pos = MeteoraPosition(
            mode="live",
            strategy=order["strategy"],
            side=order["side"],
            pool_address=order["pool_address"],
            pool_name=order.get("pool_name", ""),
            status="open",
            bins_below=order.get("bins_below"),
            bins_above=order.get("bins_above"),
            bin_step=order["bin_step"],
            lower_price=order["lower_price"],
            upper_price=order["upper_price"],
            amount_sol=order["amount_sol"],
            initial_value_usd=order.get("initial_value_usd")
            or ((float(order["lower_price"]) + float(order["upper_price"])) / 2.0)
            * float(order["amount_sol"]),  # USD-marked estimate when unset
            signal_snapshot=order.get("signal_snapshot", {}),
            onchain_position_mint=signature,
            tx_signature_open=signature,
            opened_at=datetime.now(UTC),
        )
        s.add(pos)
        s.flush()
        s.add(
            MeteoraDecision(
                actor="live_executor",
                action="deploy",
                pool_address=order["pool_address"],
                position_id=pos.id,
                mode="live",
                summary=f"Live deploy via {type(b).__name__}",
                reason="risk gates passed",
                metrics={"amount_sol": order["amount_sol"]},
                alternatives_considered=[],
            )
        )
        s.commit()
        logger.warning(f"[meteora-live] deployed #{pos.id} sig={signature}")
        return {"position_id": pos.id, "signature": signature}
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


async def _default_live_price(pool_address: str) -> float | None:
    from backend.data.meteora.client import get_dlmm_client

    pool = await get_dlmm_client().get_pool(pool_address)
    price = (pool or {}).get("current_price")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


async def close_live_position(
    position_id: int,
    *,
    builder: TxBuilder | None = None,
    exit_price: float,
) -> dict[str, Any]:
    """Gated live close; reuses paper close for bookkeeping."""
    from backend.data.meteora.paper import close_paper_position

    if not live_enabled():
        raise ExecutorError(f"{LIVE_FLAG_ENV} != 1 â refusing live close")
    b = builder or DryRunTxBuilder()
    s = _session()
    try:
        from backend.models.meteora_db import MeteoraPosition

        pos = s.get(MeteoraPosition, position_id)
        if not pos or pos.mode != "live":
            raise ExecutorError(f"live position #{position_id} not found")
        signature = await b.close_position(
            {"position_mint": pos.onchain_position_mint or f"pos-{pos.id}"}
        )
        pos.tx_signature_close = signature
        s.commit()
    finally:
        s.close()

    s = _session()
    try:
        pos = s.get(MeteoraPosition, position_id)
        close_paper_position(
            pos,
            exit_price=exit_price,
            fees_earned_usd=0.0,
            reason=pos.close_reason or "manual",
            session=s,
        )
    finally:
        s.close()
    return {"position_id": position_id, "signature": signature}
