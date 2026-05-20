"""Verify Phase 2 modules wire into orchestrator + scheduler with feature flags."""

from backend.config import settings


def test_orchestrator_imports_with_all_flags_off(monkeypatch):
    monkeypatch.setattr(settings, "WHALE_LISTENER_ENABLED", False)
    monkeypatch.setattr(settings, "NEWS_FEED_ENABLED", False)
    monkeypatch.setattr(settings, "AUTO_TRADER_ENABLED", False)
    monkeypatch.setattr(settings, "ARBITRAGE_DETECTOR_ENABLED", False)

    from backend.core.orchestrator import init_phase2_modules

    active = init_phase2_modules()
    assert active == {}


def test_init_phase2_with_arbitrage_flag(monkeypatch):
    monkeypatch.setattr(settings, "WHALE_LISTENER_ENABLED", False)
    monkeypatch.setattr(settings, "NEWS_FEED_ENABLED", False)
    monkeypatch.setattr(settings, "AUTO_TRADER_ENABLED", False)
    monkeypatch.setattr(settings, "ARBITRAGE_DETECTOR_ENABLED", True)
    from backend.core.orchestrator import init_phase2_modules

    active = init_phase2_modules()
    assert "arbitrage" in active


def test_init_phase2_with_news_feed_flag(monkeypatch):
    monkeypatch.setattr(settings, "WHALE_LISTENER_ENABLED", False)
    monkeypatch.setattr(settings, "NEWS_FEED_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_TRADER_ENABLED", False)
    monkeypatch.setattr(settings, "ARBITRAGE_DETECTOR_ENABLED", False)
    from backend.core.orchestrator import init_phase2_modules

    active = init_phase2_modules()
    assert "news_feed" in active


def test_scheduler_has_phase2_jobs():
    from backend.core import scheduler

    assert hasattr(scheduler, "news_feed_scan_job")
    assert hasattr(scheduler, "arbitrage_scan_job")
