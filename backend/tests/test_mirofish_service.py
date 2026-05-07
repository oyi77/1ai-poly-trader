import pytest
import time
from unittest.mock import patch, MagicMock
from backend.services.mirofish_service import MiroFishService, ServiceState

def test_get_status_default():
    service = MiroFishService()
    status = service.get_status()

    assert status["state"] == ServiceState.STOPPED.value
    assert status["started_at"] is None
    assert status["uptime_seconds"] is None
    assert status["last_signal_fetch"] is None
    assert status["total_signals_fetched"] == 0
    assert status["error_message"] is None
    assert "engine" in status

@patch("backend.services.mirofish_service.time.time")
def test_get_status_running(mock_time):
    # Set fixed time for deterministic tests
    mock_time.return_value = 1000.0

    # Mocking config internally in the test
    with patch("backend.config.settings") as mock_settings, \
         patch("backend.services.mirofish_monitor.get_monitor"):

        mock_settings.MIROFISH_ENABLED = False

        service = MiroFishService()

        # Override time directly before start to ensure correct uptime behavior
        mock_time.return_value = 1000.0
        service.start()

        # Advance time to simulate uptime
        mock_time.return_value = 1015.5
        status = service.get_status()

        assert status["state"] == ServiceState.RUNNING.value
        assert status["started_at"] is not None
        assert status["uptime_seconds"] == 15.5
        assert status["total_signals_fetched"] == 0
        assert status["engine"] == "builtin_debate_engine"

@patch("backend.services.mirofish_service.time.time")
def test_get_status_signal_fetch(mock_time):
    mock_time.return_value = 1000.0
    service = MiroFishService()

    with patch("backend.services.mirofish_monitor.get_monitor"):
        service.start()

        mock_time.return_value = 1050.0
        service.record_signal_fetch(count=3)

        status = service.get_status()
        assert status["total_signals_fetched"] == 3
        assert status["last_signal_fetch"] is not None

def test_get_status_external_engine():
    service = MiroFishService()

    with patch("backend.config.settings") as mock_settings:
        mock_settings.MIROFISH_ENABLED = True
        mock_settings.MIROFISH_API_URL = "http://example.com/api"

        status = service.get_status()
        assert status["engine"] == "external_mirofish_api"
        assert status["engine_url"] == "http://example.com/api"

def test_start_stop_pause():
    service = MiroFishService()

    with patch("backend.services.mirofish_monitor.get_monitor"):
        # Initial state
        assert service.state == ServiceState.STOPPED

        # Test start
        res = service.start()
        assert service.state == ServiceState.RUNNING
        assert service.is_active() is True
        assert res["state"] == ServiceState.RUNNING.value
        assert "Started" in res["message"]

        # Test start when already running
        res = service.start()
        assert "Already running" in res["message"]

        # Test pause
        res = service.pause()
        assert service.state == ServiceState.PAUSED
        assert service.is_active() is False
        assert "Paused" in res["message"]

        # Test pause when already paused
        res = service.pause()
        assert "Already paused" in res["message"]

        # Test stop
        res = service.stop()
        assert service.state == ServiceState.STOPPED
        assert "Stopped" in res["message"]

        # Test stop when already stopped
        res = service.stop()
        assert "Already stopped" in res["message"]

        # Test pause when stopped
        res = service.pause()
        assert "Cannot pause" in res["message"]

def test_restart():
    service = MiroFishService()

    with patch("backend.services.mirofish_monitor.reset_monitor"):
        # Test restart
        res = service.restart()
        assert service.state == ServiceState.RUNNING
        assert service.is_active() is True
        assert "Restarted" in res["message"]

def test_record_error():
    service = MiroFishService()
    service.record_error("Test error")
    status = service.get_status()
    assert status["error_message"] == "Test error"

def test_get_mirofish_service():
    from backend.services.mirofish_service import get_mirofish_service
    # Test singleton
    svc1 = get_mirofish_service()
    svc2 = get_mirofish_service()
    assert svc1 is svc2
