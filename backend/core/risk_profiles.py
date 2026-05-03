"""Static risk profiles per ADR-005.

Four operator-selectable presets (safe, normal, aggressive, extreme) that
overlay runtime settings consumed by RiskManager.  Profile definitions are
code-only — changing limits requires code review.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("trading_bot.risk_profiles")


@dataclass(frozen=True)
class RiskProfile:
    name: str
    display_name: str
    kelly_fraction: float
    min_edge_threshold: float
    max_trade_size: float
    max_position_fraction: float
    max_total_exposure_fraction: float
    daily_loss_limit: float
    daily_drawdown_limit_pct: float
    weekly_drawdown_limit_pct: float
    slippage_tolerance: float
    auto_approve_min_confidence: float


PROFILES: Dict[str, RiskProfile] = {
    "safe": RiskProfile(
        name="safe",
        display_name="Safe",
        kelly_fraction=0.10,
        min_edge_threshold=0.40,
        max_trade_size=3.0,
        max_position_fraction=0.03,
        max_total_exposure_fraction=0.30,
        daily_loss_limit=2.0,
        daily_drawdown_limit_pct=0.05,
        weekly_drawdown_limit_pct=0.10,
        slippage_tolerance=0.01,
        auto_approve_min_confidence=0.70,
    ),
    "normal": RiskProfile(
        name="normal",
        display_name="Normal",
        kelly_fraction=0.30,
        min_edge_threshold=0.30,
        max_trade_size=8.0,
        max_position_fraction=0.08,
        max_total_exposure_fraction=0.70,
        daily_loss_limit=5.0,
        daily_drawdown_limit_pct=0.10,
        weekly_drawdown_limit_pct=0.20,
        slippage_tolerance=0.02,
        auto_approve_min_confidence=0.50,
    ),
    "aggressive": RiskProfile(
        name="aggressive",
        display_name="Aggressive",
        kelly_fraction=0.50,
        min_edge_threshold=0.15,
        max_trade_size=20.0,
        max_position_fraction=0.15,
        max_total_exposure_fraction=0.85,
        daily_loss_limit=15.0,
        daily_drawdown_limit_pct=0.20,
        weekly_drawdown_limit_pct=0.35,
        slippage_tolerance=0.03,
        auto_approve_min_confidence=0.35,
    ),
    "extreme": RiskProfile(
        name="extreme",
        display_name="Extreme",
        kelly_fraction=0.80,
        min_edge_threshold=0.05,
        max_trade_size=50.0,
        max_position_fraction=0.25,
        max_total_exposure_fraction=0.95,
        daily_loss_limit=40.0,
        daily_drawdown_limit_pct=0.40,
        weekly_drawdown_limit_pct=0.60,
        slippage_tolerance=0.05,
        auto_approve_min_confidence=0.20,
    ),
}

DEFAULT_PROFILE = "normal"


def get_active_profile_name() -> str:
    return os.environ.get("RISK_PROFILE", DEFAULT_PROFILE)


def get_profile(name: Optional[str] = None) -> RiskProfile:
    key = name or get_active_profile_name()
    profile = PROFILES.get(key)
    if profile is None:
        logger.warning(f"[risk_profiles] Unknown profile '{key}', falling back to '{DEFAULT_PROFILE}'")
        profile = PROFILES[DEFAULT_PROFILE]
    return profile


def apply_profile(name: Optional[str] = None) -> RiskProfile:
    """Apply risk profile to runtime settings and persist name to .env."""
    from backend.config import settings

    profile = get_profile(name)
    settings.KELLY_FRACTION = profile.kelly_fraction
    settings.MIN_EDGE_THRESHOLD = profile.min_edge_threshold
    settings.MAX_TRADE_SIZE = profile.max_trade_size
    settings.MAX_POSITION_FRACTION = profile.max_position_fraction
    settings.MAX_TOTAL_EXPOSURE_FRACTION = profile.max_total_exposure_fraction
    settings.DAILY_LOSS_LIMIT = profile.daily_loss_limit
    settings.DAILY_DRAWDOWN_LIMIT_PCT = profile.daily_drawdown_limit_pct
    settings.WEEKLY_DRAWDOWN_LIMIT_PCT = profile.weekly_drawdown_limit_pct
    settings.SLIPPAGE_TOLERANCE = profile.slippage_tolerance
    settings.AUTO_APPROVE_MIN_CONFIDENCE = profile.auto_approve_min_confidence

    _persist_profile_name(profile.name)

    logger.info(f"[risk_profiles] Applied profile '{profile.display_name}' to runtime settings")
    return profile


def _persist_profile_name(name: str) -> None:
    try:
        env_path = os.path.join(os.getcwd(), ".env")
        lines: list[str] = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith("RISK_PROFILE="):
                lines[i] = f"RISK_PROFILE={name}\n"
                found = True
                break
        if not found:
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(f"RISK_PROFILE={name}\n")

        with open(env_path, "w") as f:
            f.writelines(lines)
        os.environ["RISK_PROFILE"] = name
    except Exception as e:
        logger.warning(f"[risk_profiles] Failed to persist RISK_PROFILE to .env: {e}")
