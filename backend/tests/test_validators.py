"""
Tests for backend/data/validators.py — Pydantic v2 validation models.
"""
import time
import pytest
from pydantic import ValidationError

from backend.data.validators import (
    GammaMarketResponse,
    CLOBOrderBookResponse,
    CoinbaseKlineResponse,
    OpenMeteoForecastResponse,
    validate_response,
)
from backend.core.errors import DataQualityError


# ---------------------------------------------------------------------------
# Fixtures / shared helpers
# ---------------------------------------------------------------------------

def _valid_gamma():
    return {
        "id": 42,
        "question": "Will ETH reach $5000 by end of year?",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.65", "0.35"],
        "volume": 12345.67,
        "active": True,
        "closed": False,
    }


def _valid_kline():
    return {
        "timestamp": int(time.time()) - 3600,
        "open": 60000.0,
        "high": 61000.0,
        "low": 59000.0,
        "close": 60500.0,
        "volume": 100.0,
    }


def _valid_forecast():
    return {
        "hourly": {
            "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
            "temperature_2m": [15.0, 16.5],
        }
    }


# ---------------------------------------------------------------------------
# GammaMarketResponse
# ---------------------------------------------------------------------------

def test_gamma_market_valid():
    m = GammaMarketResponse.model_validate(_valid_gamma())
    assert m.id == 42
    assert m.question == "Will ETH reach $5000 by end of year?"
    assert m.outcomes == ["Yes", "No"]
    assert m.volume == 12345.67
    assert m.active is True
    assert m.slug is None


def test_gamma_market_missing_field():
    data = _valid_gamma()
    del data["question"]
    with pytest.raises(ValidationError) as exc_info:
        GammaMarketResponse.model_validate(data)
    errors = exc_info.value.errors()
    field_locs = [e["loc"] for e in errors]
    assert any("question" in loc for loc in field_locs)


def test_gamma_market_price_out_of_range():
    data = _valid_gamma()
    data["outcomePrices"] = ["1.5", "-0.5"]
    with pytest.raises(ValidationError) as exc_info:
        GammaMarketResponse.model_validate(data)
    assert any("outcomePrices" in str(e["loc"]) for e in exc_info.value.errors())


def test_gamma_market_outcomes_too_few():
    data = _valid_gamma()
    data["outcomes"] = ["Yes"]
    with pytest.raises(ValidationError):
        GammaMarketResponse.model_validate(data)


def test_gamma_market_negative_volume():
    data = _valid_gamma()
    data["volume"] = -1.0
    with pytest.raises(ValidationError):
        GammaMarketResponse.model_validate(data)


def test_gamma_market_optional_fields_present():
    data = _valid_gamma()
    data["slug"] = "eth-5k"
    data["conditionId"] = "0xabc"
    data["endDate"] = "2024-12-31"
    m = GammaMarketResponse.model_validate(data)
    assert m.slug == "eth-5k"
    assert m.conditionId == "0xabc"
    assert m.endDate == "2024-12-31"


# ---------------------------------------------------------------------------
# CoinbaseKlineResponse
# ---------------------------------------------------------------------------

def test_coinbase_kline_valid():
    m = CoinbaseKlineResponse.model_validate(_valid_kline())
    assert m.open == 60000.0
    assert m.high == 61000.0
    assert m.low == 59000.0
    assert m.close == 60500.0
    assert m.volume == 100.0


def test_coinbase_kline_high_less_than_low():
    data = _valid_kline()
    data["high"] = 58000.0  # below low of 59000
    with pytest.raises(ValidationError) as exc_info:
        CoinbaseKlineResponse.model_validate(data)
    messages = " ".join(e["msg"] for e in exc_info.value.errors())
    assert "high" in messages and "low" in messages


def test_coinbase_kline_high_less_than_open():
    data = _valid_kline()
    data["open"] = 62000.0  # above high of 61000
    with pytest.raises(ValidationError):
        CoinbaseKlineResponse.model_validate(data)


def test_coinbase_kline_future_timestamp():
    data = _valid_kline()
    data["timestamp"] = int(time.time()) + 3600
    with pytest.raises(ValidationError):
        CoinbaseKlineResponse.model_validate(data)


def test_coinbase_kline_zero_price():
    data = _valid_kline()
    data["open"] = 0.0
    with pytest.raises(ValidationError):
        CoinbaseKlineResponse.model_validate(data)


# ---------------------------------------------------------------------------
# OpenMeteoForecastResponse
# ---------------------------------------------------------------------------

def test_open_meteo_valid():
    m = OpenMeteoForecastResponse.model_validate(_valid_forecast())
    assert m.hourly.time == ["2024-01-01T00:00", "2024-01-01T01:00"]
    assert m.hourly.temperature_2m == [15.0, 16.5]


def test_open_meteo_temperature_out_of_range():
    data = _valid_forecast()
    data["hourly"]["temperature_2m"] = [15.0, 75.0]  # 75 > 60
    with pytest.raises(ValidationError) as exc_info:
        OpenMeteoForecastResponse.model_validate(data)
    messages = " ".join(e["msg"] for e in exc_info.value.errors())
    assert "60" in messages or "range" in messages


def test_open_meteo_temperature_below_min():
    data = _valid_forecast()
    data["hourly"]["temperature_2m"] = [-90.0, 15.0]  # -90 < -80
    with pytest.raises(ValidationError):
        OpenMeteoForecastResponse.model_validate(data)


def test_open_meteo_mismatched_lengths():
    data = _valid_forecast()
    data["hourly"]["temperature_2m"] = [15.0]  # time has 2 entries, temps has 1
    with pytest.raises(ValidationError) as exc_info:
        OpenMeteoForecastResponse.model_validate(data)
    messages = " ".join(e["msg"] for e in exc_info.value.errors())
    assert "length" in messages or "same" in messages


def test_open_meteo_missing_hourly():
    with pytest.raises(ValidationError):
        OpenMeteoForecastResponse.model_validate({})


# ---------------------------------------------------------------------------
# CLOBOrderBookResponse
# ---------------------------------------------------------------------------

def test_clob_order_book_valid():
    data = {
        "bids": [{"price": "0.55", "size": "100.0"}],
        "asks": [{"price": "0.60", "size": "50.0"}],
        "timestamp": 1700000000,
    }
    m = CLOBOrderBookResponse.model_validate(data)
    assert len(m.bids) == 1
    assert len(m.asks) == 1
    assert m.timestamp == 1700000000


def test_clob_order_book_price_out_of_range():
    data = {
        "bids": [{"price": "1.5", "size": "100.0"}],
        "asks": [],
    }
    with pytest.raises(ValidationError):
        CLOBOrderBookResponse.model_validate(data)


def test_clob_order_book_size_zero():
    data = {
        "bids": [{"price": "0.5", "size": "0.0"}],
        "asks": [],
    }
    with pytest.raises(ValidationError):
        CLOBOrderBookResponse.model_validate(data)


# ---------------------------------------------------------------------------
# validate_response helper
# ---------------------------------------------------------------------------

def test_validate_response_helper_success():
    result = validate_response(GammaMarketResponse, _valid_gamma(), source="test")
    assert isinstance(result, GammaMarketResponse)


def test_validate_response_helper():
    """Helper raises DataQualityError when data is invalid."""
    bad_data = {"id": 1}  # missing many required fields
    with pytest.raises(DataQualityError) as exc_info:
        validate_response(GammaMarketResponse, bad_data, source="gamma-api")
    err = exc_info.value
    assert "gamma-api" in err.details.get("source", "")
    assert err.details.get("field_errors")


def test_validate_response_helper_error_details():
    """DataQualityError details contain per-field information."""
    bad_data = _valid_gamma()
    bad_data["outcomePrices"] = ["2.0"]  # out of range
    with pytest.raises(DataQualityError) as exc_info:
        validate_response(GammaMarketResponse, bad_data, source="test-source")
    assert "field_errors" in exc_info.value.details
