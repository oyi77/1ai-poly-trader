"""Tests for backend/monitoring/queue_metrics.py (RQ-016)."""

import pytest
import backend.monitoring.queue_metrics as _metrics_mod
from backend.monitoring.queue_metrics import QueueMetrics, JobTimer


def test_records_latency_and_percentiles():
    m = QueueMetrics()
    for i in range(1, 101):  # 1..100 ms
        m.record_job_completion("scan", float(i), "success")
    p = m.percentiles("scan")
    # p50 should be ~50, p95 ~95, p99 ~99
    assert 45 <= p["p50"] <= 55, f"p50={p['p50']}"
    assert 90 <= p["p95"] <= 100, f"p95={p['p95']}"
    assert 95 <= p["p99"] <= 100, f"p99={p['p99']}"


def test_timeout_rate_calculated():
    m = QueueMetrics()
    for _ in range(8):
        m.record_job_completion("scan", 10.0, "success")
    for _ in range(2):
        m.record_job_completion("scan", 10.0, "timeout")
    snap = m.get_metrics_snapshot()
    assert snap["by_type"]["scan"]["timeout_rate"] == pytest.approx(0.2)


def test_error_rate_calculated():
    m = QueueMetrics()
    for _ in range(7):
        m.record_job_completion("scan", 10.0, "success")
    for _ in range(3):
        m.record_job_completion("scan", 10.0, "error")
    snap = m.get_metrics_snapshot()
    assert snap["by_type"]["scan"]["error_rate"] == pytest.approx(0.3)


def test_update_depth_reflected_in_snapshot():
    m = QueueMetrics()
    m.update_depth(42)
    snap = m.get_metrics_snapshot()
    assert snap["depth"] == 42


def test_job_timer_context_manager():
    # Use a fresh isolated QueueMetrics so global state doesn't interfere
    fresh = QueueMetrics()
    original = _metrics_mod._global_metrics
    _metrics_mod._global_metrics = fresh
    try:
        with JobTimer("test") as t:
            t.status = "success"
        snap = fresh.get_metrics_snapshot()
        assert "test" in snap["by_type"]
        assert snap["by_type"]["test"]["total"] == 1
        assert snap["by_type"]["test"]["successes"] == 1
        assert snap["by_type"]["test"]["timeout_rate"] == 0.0
    finally:
        _metrics_mod._global_metrics = original
