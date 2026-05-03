"""Tests for static risk profiles per ADR-005."""

import os
import pytest
from unittest.mock import patch, MagicMock

from backend.core.risk_profiles import (
    PROFILES,
    RiskProfile,
    DEFAULT_PROFILE,
    get_profile,
    get_active_profile_name,
    apply_profile,
)


class TestProfileDefinitions:
    def test_four_profiles_exist(self):
        assert set(PROFILES.keys()) == {"safe", "normal", "aggressive", "extreme"}

    def test_default_is_normal(self):
        assert DEFAULT_PROFILE == "normal"

    def test_profiles_have_monotonic_risk(self):
        safe = PROFILES["safe"]
        normal = PROFILES["normal"]
        aggressive = PROFILES["aggressive"]
        extreme = PROFILES["extreme"]

        assert safe.kelly_fraction < normal.kelly_fraction < aggressive.kelly_fraction < extreme.kelly_fraction
        assert safe.max_trade_size < normal.max_trade_size < aggressive.max_trade_size < extreme.max_trade_size
        assert safe.max_position_fraction < normal.max_position_fraction < aggressive.max_position_fraction < extreme.max_position_fraction
        assert safe.daily_drawdown_limit_pct < normal.daily_drawdown_limit_pct < aggressive.daily_drawdown_limit_pct < extreme.daily_drawdown_limit_pct

    def test_normal_has_expected_values(self):
        normal = PROFILES["normal"]
        assert normal.kelly_fraction == 0.30
        assert normal.daily_loss_limit == 5.0
        assert normal.max_position_fraction == 0.08
        assert normal.max_total_exposure_fraction == 0.70
        assert normal.daily_drawdown_limit_pct == 0.10
        assert normal.weekly_drawdown_limit_pct == 0.20
        assert normal.slippage_tolerance == 0.02


class TestGetProfile:
    def test_get_by_name(self):
        p = get_profile("safe")
        assert p.name == "safe"

    def test_get_default_when_none(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RISK_PROFILE", None)
            p = get_profile(None)
            assert p.name == DEFAULT_PROFILE

    def test_get_unknown_falls_back(self):
        p = get_profile("nonexistent")
        assert p.name == DEFAULT_PROFILE

    def test_active_profile_from_env(self):
        with patch.dict(os.environ, {"RISK_PROFILE": "aggressive"}):
            name = get_active_profile_name()
            assert name == "aggressive"


class TestApplyProfile:
    def test_apply_safe(self):
        from backend.config import settings
        original_kelly = settings.KELLY_FRACTION

        profile = apply_profile("safe")
        assert profile.name == "safe"
        assert settings.KELLY_FRACTION == PROFILES["safe"].kelly_fraction
        assert settings.MAX_POSITION_FRACTION == PROFILES["safe"].max_position_fraction
        assert settings.DAILY_DRAWDOWN_LIMIT_PCT == PROFILES["safe"].daily_drawdown_limit_pct

        settings.KELLY_FRACTION = original_kelly

    def test_apply_sets_env_var(self):
        with patch.dict(os.environ, {}, clear=False):
            apply_profile("extreme")
            assert os.environ.get("RISK_PROFILE") == "extreme"

            os.environ.pop("RISK_PROFILE", None)
