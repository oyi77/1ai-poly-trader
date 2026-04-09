"""Tests for backend/ai/market_analyzer.py"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.ai.market_analyzer import (
    AIAnalysis,
    _parse_ai_response,
    analyze_market,
    check_ai_budget,
)


# ---------------------------------------------------------------------------
# _parse_ai_response tests
# ---------------------------------------------------------------------------


def test_parse_ai_response_structured():
    """Parse standard PROBABILITY/CONFIDENCE/REASONING format."""
    text = (
        "PROBABILITY: 0.65\n"
        "CONFIDENCE: 0.8\n"
        "REASONING: Strong momentum and low volatility support YES outcome."
    )
    prob, conf, reasoning = _parse_ai_response(text)
    assert prob == pytest.approx(0.65)
    assert conf == pytest.approx(0.8)
    assert "momentum" in reasoning.lower()


def test_parse_ai_response_json():
    """Parse JSON format response."""
    data = {
        "probability": 0.65,
        "confidence": 0.75,
        "reasoning": "Market fundamentals favor YES.",
    }
    text = json.dumps(data)
    prob, conf, reasoning = _parse_ai_response(text)
    assert prob == pytest.approx(0.65)
    assert conf == pytest.approx(0.75)
    assert "fundamentals" in reasoning.lower()


def test_parse_ai_response_json_embedded():
    """Parse JSON embedded in prose text."""
    data = {"probability": 0.3, "confidence": 0.9, "reasoning": "Unlikely event."}
    text = f"Here is my analysis: {json.dumps(data)} Hope that helps."
    prob, conf, reasoning = _parse_ai_response(text)
    assert prob == pytest.approx(0.3)
    assert conf == pytest.approx(0.9)


def test_parse_handles_malformed():
    """Handles garbage input gracefully — returns neutral fallback."""
    result = _parse_ai_response("lkjasldfkj 123 !!!! gibberish")
    prob, conf, reasoning = result
    # Should not raise; returns fallback probability and zero confidence
    assert isinstance(prob, float)
    assert isinstance(conf, float)
    assert 0.0 <= prob <= 1.0
    assert conf == 0.0  # parse failed sentinel


def test_parse_clamps_out_of_range_values():
    """Values outside [0,1] are clamped."""
    text = "PROBABILITY: 1.5\nCONFIDENCE: -0.2\nREASONING: test"
    prob, conf, reasoning = _parse_ai_response(text)
    assert prob == pytest.approx(1.0)
    assert conf == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# analyze_market tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_market_returns_analysis():
    """Mock AI provider, verify AIAnalysis is returned with correct fields."""
    groq_text = "PROBABILITY: 0.40\nCONFIDENCE: 0.75\nREASONING: Price action bearish."

    with (
        patch("backend.ai.market_analyzer._call_groq", new=AsyncMock(return_value=groq_text)),
        patch(
            "backend.ai.market_analyzer.check_ai_budget",
            new=AsyncMock(return_value={"spent_today": 0.01, "limit": 1.0, "remaining": 0.99, "can_call": True}),
        ),
        patch(
            "backend.ai.market_analyzer.get_ai_logger",
            return_value=MagicMock(get_daily_stats=MagicMock(return_value={"total_cost_usd": 0.01})),
        ),
    ):
        result = await analyze_market(
            question="Will BTC close above $70k?",
            current_price=0.45,
            volume=5000.0,
            category="crypto",
        )

    assert result is not None
    assert isinstance(result, AIAnalysis)
    assert result.probability == pytest.approx(0.40)
    assert result.confidence == pytest.approx(0.75)
    assert result.provider == "groq"
    assert "bearish" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_budget_exceeded_returns_none():
    """When budget is exceeded, analyze_market returns None immediately."""
    with patch(
        "backend.ai.market_analyzer.check_ai_budget",
        new=AsyncMock(return_value={"spent_today": 1.05, "limit": 1.0, "remaining": 0.0, "can_call": False}),
    ):
        result = await analyze_market(
            question="Will it rain in NYC?",
            current_price=0.5,
            volume=100.0,
        )

    assert result is None


@pytest.mark.asyncio
async def test_groq_api_error_returns_none():
    """When Groq raises / returns None, analyze_market returns None."""
    with (
        patch("backend.ai.market_analyzer._call_groq", new=AsyncMock(return_value=None)),
        patch(
            "backend.ai.market_analyzer.check_ai_budget",
            new=AsyncMock(return_value={"spent_today": 0.0, "limit": 1.0, "remaining": 1.0, "can_call": True}),
        ),
    ):
        result = await analyze_market(
            question="Will ETH hit $5k?",
            current_price=0.3,
            volume=200.0,
        )

    assert result is None


@pytest.mark.asyncio
async def test_escalates_to_claude_when_edge_large():
    """When Groq returns edge > 5%, Claude is called for deeper analysis."""
    # current_price=0.45, groq_prob=0.72 => edge=0.27 > 0.05 => escalate
    groq_text = "PROBABILITY: 0.72\nCONFIDENCE: 0.6\nREASONING: Strong signal."
    claude_text = "PROBABILITY: 0.70\nCONFIDENCE: 0.85\nREASONING: Claude deep analysis."

    budget_ok = {"spent_today": 0.01, "limit": 1.0, "remaining": 0.99, "can_call": True}

    with (
        patch("backend.ai.market_analyzer._call_groq", new=AsyncMock(return_value=groq_text)),
        patch("backend.ai.market_analyzer._call_claude", new=AsyncMock(return_value=claude_text)),
        patch("backend.ai.market_analyzer.check_ai_budget", new=AsyncMock(return_value=budget_ok)),
    ):
        result = await analyze_market(
            question="Will BTC double?",
            current_price=0.45,
            volume=9999.0,
            category="crypto",
        )

    assert result is not None
    assert result.provider == "claude"
    assert result.probability == pytest.approx(0.70)
    assert result.confidence == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# check_ai_budget tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_ai_budget_structure():
    """check_ai_budget returns required keys with correct types."""
    mock_logger = MagicMock()
    mock_logger.get_daily_stats.return_value = {"total_cost_usd": 0.25}

    with (
        patch("backend.ai.market_analyzer.get_ai_logger", return_value=mock_logger),
        patch("backend.config.settings") as mock_settings,
    ):
        mock_settings.AI_DAILY_BUDGET_USD = 1.0
        # Re-patch within module namespace
        with patch("backend.ai.market_analyzer.check_ai_budget", wraps=check_ai_budget):
            pass

    # Call with real implementation but mocked logger
    with patch("backend.ai.market_analyzer.get_ai_logger", return_value=mock_logger):
        result = await check_ai_budget()

    assert "spent_today" in result
    assert "limit" in result
    assert "remaining" in result
    assert "can_call" in result
    assert isinstance(result["can_call"], bool)
    assert result["remaining"] >= 0.0
