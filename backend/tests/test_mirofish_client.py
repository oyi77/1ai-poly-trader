"""Unit tests for MiroFish API client."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from backend.ai.mirofish_client import (
    MiroFishClient,
    MiroFishSignal,
    ErrorResponse,
)


@pytest.fixture
def mock_settings():
    with patch("backend.core.config_service.get_setting") as mock:
        mock.side_effect = lambda key, default: {
            "MIROFISH_API_URL": "https://test.mirofish.ai",
            "MIROFISH_API_KEY": "test_key_123",
            "MIROFISH_API_TIMEOUT": 10.0,
        }.get(key, default)
        yield mock


@pytest.fixture
def client(mock_settings):
    return MiroFishClient()


@pytest.fixture
def mock_response_data():
    return {
        "signals": [
            {
                "market_id": "0xabc123",
                "prediction": 0.75,
                "confidence": 0.92,
                "reasoning": "Strong bullish momentum",
                "source": "mirofish",
            },
            {
                "market_id": "0xdef456",
                "prediction": 0.45,
                "confidence": 0.78,
                "reasoning": "Weak bearish signals",
                "source": "mirofish",
            },
        ]
    }


@pytest.mark.asyncio
async def test_client_initialization(mock_settings):
    client = MiroFishClient()
    
    assert client.api_url == "https://test.mirofish.ai"
    assert client.api_key == "test_key_123"
    assert client.timeout == 10.0
    assert client._consecutive_failures == 0
    assert client._circuit_open is False


@pytest.mark.asyncio
async def test_client_initialization_with_overrides():
    client = MiroFishClient(
        api_url="https://custom.api",
        api_key="custom_key",
        timeout=20.0,
    )
    
    assert client.api_url == "https://custom.api"
    assert client.api_key == "custom_key"
    assert client.timeout == 20.0


@pytest.mark.asyncio
async def test_fetch_signals_success(client, mock_response_data):
    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_response)
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        signals = await client.fetch_signals(market="polymarket")
    
    assert len(signals) == 2
    assert isinstance(signals[0], MiroFishSignal)
    assert signals[0].market_id == "0xabc123"
    assert signals[0].prediction == 0.75
    assert signals[0].confidence == 0.92
    assert signals[0].reasoning == "Strong bullish momentum"
    assert signals[0].source == "mirofish"
    
    assert signals[1].market_id == "0xdef456"
    assert signals[1].prediction == 0.45
    
    mock_http_client.get.assert_called_once_with(
        "https://test.mirofish.ai/api/signals",
        params={"market": "polymarket"}
    )


@pytest.mark.asyncio
async def test_fetch_signals_empty_response(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"signals": []}
    mock_response.raise_for_status = MagicMock()
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_response)
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        signals = await client.fetch_signals()
    
    assert signals == []
    assert client._consecutive_failures == 0


@pytest.mark.asyncio
async def test_fetch_signals_timeout_with_retry(client):
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        with patch.object(client, "_async_sleep", new_callable=AsyncMock):
            signals = await client.fetch_signals()
    
    assert signals == []
    assert mock_http_client.get.call_count == 3
    assert client._consecutive_failures == 3


@pytest.mark.asyncio
async def test_fetch_signals_http_500_with_retry(client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=mock_response
        )
    )
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        with patch.object(client, "_async_sleep", new_callable=AsyncMock):
            signals = await client.fetch_signals()
    
    assert signals == []
    assert mock_http_client.get.call_count == 3
    assert client._consecutive_failures == 3


@pytest.mark.asyncio
async def test_fetch_signals_http_400_no_retry(client):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Bad request",
            request=MagicMock(),
            response=mock_response
        )
    )
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        signals = await client.fetch_signals()
    
    assert signals == []
    assert mock_http_client.get.call_count == 1
    assert client._consecutive_failures == 1


@pytest.mark.asyncio
async def test_fetch_signals_success_after_retry(client, mock_response_data):
    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(
        side_effect=[
            httpx.TimeoutException("Timeout"),
            mock_response,
        ]
    )
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        with patch.object(client, "_async_sleep", new_callable=AsyncMock):
            signals = await client.fetch_signals()
    
    assert len(signals) == 2
    assert mock_http_client.get.call_count == 2
    assert client._consecutive_failures == 0


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_5_failures(client):
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        with patch.object(client, "_async_sleep", new_callable=AsyncMock):
            await client.fetch_signals()
            await client.fetch_signals()
    
    assert client._consecutive_failures == 6
    
    signals = await client.fetch_signals()
    assert signals == []
    assert client._circuit_open is True
    assert mock_http_client.get.call_count == 6


@pytest.mark.asyncio
async def test_circuit_breaker_reset(client):
    client._consecutive_failures = 10
    client._circuit_open = True
    
    client.reset_circuit_breaker()
    
    assert client._consecutive_failures == 0
    assert client._circuit_open is False


@pytest.mark.asyncio
async def test_validate_signal_valid(client):
    valid_signal = {
        "market_id": "0xabc123",
        "prediction": 0.75,
        "confidence": 0.92,
    }
    
    assert client.validate_signal(valid_signal) is True


@pytest.mark.asyncio
async def test_validate_signal_missing_field(client):
    invalid_signal = {
        "market_id": "0xabc123",
        "prediction": 0.75,
    }
    
    assert client.validate_signal(invalid_signal) is False


@pytest.mark.asyncio
async def test_validate_signal_invalid_prediction_range(client):
    invalid_signal = {
        "market_id": "0xabc123",
        "prediction": 1.5,
        "confidence": 0.92,
    }
    
    assert client.validate_signal(invalid_signal) is False


@pytest.mark.asyncio
async def test_validate_signal_invalid_confidence_range(client):
    invalid_signal = {
        "market_id": "0xabc123",
        "prediction": 0.75,
        "confidence": -0.1,
    }
    
    assert client.validate_signal(invalid_signal) is False


@pytest.mark.asyncio
async def test_validate_signal_invalid_market_id(client):
    invalid_signal = {
        "market_id": "",
        "prediction": 0.75,
        "confidence": 0.92,
    }
    
    assert client.validate_signal(invalid_signal) is False


@pytest.mark.asyncio
async def test_validate_signal_invalid_types(client):
    invalid_signal = {
        "market_id": "0xabc123",
        "prediction": "not_a_number",
        "confidence": 0.92,
    }
    
    assert client.validate_signal(invalid_signal) is False


@pytest.mark.asyncio
async def test_parse_signals_filters_invalid(client):
    data = {
        "signals": [
            {
                "market_id": "0xabc123",
                "prediction": 0.75,
                "confidence": 0.92,
                "reasoning": "Valid signal",
            },
            {
                "market_id": "0xdef456",
                "prediction": 1.5,
                "confidence": 0.78,
                "reasoning": "Invalid prediction",
            },
            {
                "market_id": "",
                "prediction": 0.5,
                "confidence": 0.8,
                "reasoning": "Invalid market_id",
            },
        ]
    }
    
    signals = client._parse_signals(data)
    
    assert len(signals) == 1
    assert signals[0].market_id == "0xabc123"


@pytest.mark.asyncio
async def test_handle_api_error(client):
    test_error = ValueError("Test error message")
    
    error_response = client.handle_api_error(test_error)
    
    assert isinstance(error_response, ErrorResponse)
    assert error_response.error_type == "ValueError"
    assert error_response.message == "Test error message"
    assert error_response.timestamp is not None
    assert error_response.traceback is not None


@pytest.mark.asyncio
async def test_close_client(client):
    mock_http_client = AsyncMock()
    client._client = mock_http_client
    
    await client.close()
    
    mock_http_client.aclose.assert_called_once()
    assert client._client is None


@pytest.mark.asyncio
async def test_get_client_creates_new_client(client):
    assert client._client is None
    
    http_client = await client._get_client()
    
    assert http_client is not None
    assert client._client is not None
    assert isinstance(client._client, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_get_client_reuses_existing_client(client):
    first_client = await client._get_client()
    second_client = await client._get_client()
    
    assert first_client is second_client


@pytest.mark.asyncio
async def test_fetch_signals_logs_metrics(client, mock_response_data, caplog):
    import logging
    caplog.set_level(logging.INFO)
    
    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()
    
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_response)
    
    with patch.object(client, "_get_client", return_value=mock_http_client):
        await client.fetch_signals()
    
    assert "MiroFish API success" in caplog.text
    assert "2 signals fetched" in caplog.text


@pytest.mark.asyncio
async def test_settings_integration_from_config_service(mock_settings):
    client = MiroFishClient()
    
    mock_settings.assert_any_call("MIROFISH_API_URL", "https://api.mirofish.ai")
    mock_settings.assert_any_call("MIROFISH_API_KEY", "")
    mock_settings.assert_any_call("MIROFISH_API_TIMEOUT", 30.0)
