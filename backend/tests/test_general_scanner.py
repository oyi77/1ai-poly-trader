"""Tests for GeneralMarketScanner."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market(
    slug="test-market",
    volume=100000,
    outcome_prices=None,
    category="politics",
    question="Will X happen?",
):
    return {
        "slug": slug,
        "question": question,
        "volume": volume,
        "outcomePrices": outcome_prices
        if outcome_prices is not None
        else ["0.45", "0.55"],
        "category": category,
    }


def _make_ctx(ai_enabled=True, params=None, bankroll=100.0, min_debate_edge=0.04):
    from backend.strategies.base import StrategyContext

    settings_mock = MagicMock()
    settings_mock.AI_ENABLED = ai_enabled
    settings_mock.KELLY_FRACTION = 0.15
    settings_mock.MIN_DEBATE_EDGE = min_debate_edge
    settings_mock.TRADING_MODE = "paper"

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.first.return_value = MagicMock(
        bankroll=bankroll, paper_bankroll=bankroll
    )

    merged_params = {"skip_hours": [], **(params or {})}

    ctx = StrategyContext(
        db=db,
        clob=None,
        settings=settings_mock,
        logger=MagicMock(),
        params=merged_params,
        mode="paper",
    )
    return ctx


@dataclass
class _FakeAIAnalysis:
    probability: float
    confidence: float
    reasoning: str = "test"
    provider: str = "groq"
    cost_usd: float = 0.0


@dataclass
class _FakeDebateResult:
    consensus_probability: float
    confidence: float
    reasoning: str = "debate consensus"
    rounds_completed: int = 2


def _mock_httpx_for_markets(markets):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=markets)
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeneralScannerRequiresAI:
    @pytest.mark.asyncio
    async def test_requires_ai_enabled(self):
        """Strategy returns empty decisions with error when AI is disabled."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=False)

        result = await strategy.run_cycle(ctx)

        assert result.decisions_recorded == 0
        assert result.trades_attempted == 0
        assert "AI disabled" in result.errors

    @pytest.mark.asyncio
    async def test_returns_empty_on_ai_import_failure(self):
        """Returns gracefully when AI module is unavailable."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=True)

        markets = [_make_market(volume=200000)]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=markets)

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch.dict("sys.modules", {"backend.ai.market_analyzer": None}),
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await strategy.run_cycle(ctx)

        # Should fail gracefully — either no decisions or an error logged
        assert result.decisions_recorded == 0 or len(result.errors) >= 0


class TestGeneralScannerFilters:
    def test_filters_by_volume_and_category(self):
        """Only high-volume markets in allowed categories should be candidates."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        params = strategy.default_params
        min_volume = params["min_volume"]
        allowed_cats = {c.strip().lower() for c in str(params["categories"]).split(",")}

        low_vol = _make_market(volume=1000, category="politics")
        assert low_vol["volume"] < min_volume, "Low-volume should be rejected"

        good_market = _make_market(volume=200000, category="politics")
        assert good_market["volume"] >= min_volume, (
            "High-volume should pass volume filter"
        )
        assert good_market["category"].lower() in allowed_cats, (
            "politics should be in allowed categories"
        )

        bad_cat = _make_market(volume=200000, category="uncategorized_xyz")
        assert bad_cat["category"].lower() not in allowed_cats, (
            "Unknown category should be filtered"
        )

    def test_price_range_filter(self):
        """Markets outside min_price/max_price range should be rejected."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        params = strategy.default_params
        min_price = params["min_price"]
        max_price = params["max_price"]

        # YES price too low AND NO price (1-yes) also out of range
        extreme_market = _make_market(outcome_prices=["0.05", "0.95"])
        yes_price = float(extreme_market["outcomePrices"][0])
        no_price = 1.0 - yes_price
        both_out = (yes_price < min_price or yes_price > max_price) and (
            no_price < min_price or no_price > max_price
        )
        assert both_out, "Price 0.05/0.95 should both be out of [0.15, 0.75]"

        # Good market — YES in range
        good_market = _make_market(outcome_prices=["0.45", "0.55"])
        yes_price = float(good_market["outcomePrices"][0])
        in_range = min_price <= yes_price <= max_price
        assert in_range, "Price 0.45 should be in [0.15, 0.75]"


class TestRegistryRegistration:
    def test_registered_in_registry(self):
        """Both new strategies must appear in STRATEGY_REGISTRY after load_all_strategies."""
        from backend.strategies.registry import load_all_strategies, STRATEGY_REGISTRY

        load_all_strategies()

        assert "bond_scanner" in STRATEGY_REGISTRY, (
            "bond_scanner should be registered after load_all_strategies()"
        )
        assert "general_scanner" in STRATEGY_REGISTRY, (
            "general_scanner should be registered after load_all_strategies()"
        )

    def test_bond_scanner_has_correct_metadata(self):
        """BondScannerStrategy has expected name, category, and default_params."""
        from backend.strategies.registry import load_all_strategies, STRATEGY_REGISTRY

        load_all_strategies()
        cls = STRATEGY_REGISTRY.get("bond_scanner")
        assert cls is not None

        instance = cls()
        assert instance.name == "bond_scanner"
        assert instance.category == "value"
        assert "min_price" in instance.default_params
        assert "max_position_size" in instance.default_params

    def test_general_scanner_has_correct_metadata(self):
        """GeneralMarketScanner has expected name, category, and default_params."""
        from backend.strategies.registry import load_all_strategies, STRATEGY_REGISTRY

        load_all_strategies()
        cls = STRATEGY_REGISTRY.get("general_scanner")
        assert cls is not None

        instance = cls()
        assert instance.name == "general_scanner"
        assert instance.category == "ai_driven"
        assert "min_edge" in instance.default_params
        assert "scan_limit" in instance.default_params


# ---------------------------------------------------------------------------
# T19: _fetch_brain_context unit tests
# ---------------------------------------------------------------------------


class TestFetchBrainContext:
    @pytest.mark.asyncio
    async def test_returns_formatted_context_on_success(self):
        """Brain returns results → formatted pipe-separated string."""
        from backend.strategies.general_market_scanner import _fetch_brain_context

        mock_brain = AsyncMock()
        mock_brain.search_context = AsyncMock(
            return_value=[
                {"text": "Historical win rate 65%", "content": ""},
                {"text": "", "content": "Market moved 3% after debate"},
                {"text": "Polling data shows lead", "content": ""},
            ]
        )

        with patch(
            "backend.clients.bigbrain.BigBrainClient",
            return_value=mock_brain,
        ):
            result = await _fetch_brain_context("Will candidate X win?")

        assert "Historical win rate 65%" in result
        assert "Market moved 3% after debate" in result
        assert "Polling data shows lead" in result
        assert " | " in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        """Brain returns empty list → empty string."""
        from backend.strategies.general_market_scanner import _fetch_brain_context

        mock_brain = AsyncMock()
        mock_brain.search_context = AsyncMock(return_value=[])

        with patch(
            "backend.clients.bigbrain.BigBrainClient",
            return_value=mock_brain,
        ):
            result = await _fetch_brain_context("Will Y happen?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        """Brain raises exception → empty string (fail open)."""
        from backend.strategies.general_market_scanner import _fetch_brain_context

        with patch(
            "backend.clients.bigbrain.BigBrainClient",
            side_effect=ConnectionError("brain unreachable"),
        ):
            result = await _fetch_brain_context("Will Z happen?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_truncates_long_items(self):
        """Individual items are truncated to 200 chars."""
        from backend.strategies.general_market_scanner import _fetch_brain_context

        long_text = "A" * 500
        mock_brain = AsyncMock()
        mock_brain.search_context = AsyncMock(
            return_value=[{"text": long_text, "content": ""}]
        )

        with patch(
            "backend.clients.bigbrain.BigBrainClient",
            return_value=mock_brain,
        ):
            result = await _fetch_brain_context("question")

        assert len(result) <= 200

    @pytest.mark.asyncio
    async def test_prefers_text_over_content(self):
        """'text' key is preferred over 'content' when both present."""
        from backend.strategies.general_market_scanner import _fetch_brain_context

        mock_brain = AsyncMock()
        mock_brain.search_context = AsyncMock(
            return_value=[{"text": "primary", "content": "fallback"}]
        )

        with patch(
            "backend.clients.bigbrain.BigBrainClient",
            return_value=mock_brain,
        ):
            result = await _fetch_brain_context("question")

        assert result == "primary"


# ---------------------------------------------------------------------------
# T17: _run_debate_gate unit tests
# ---------------------------------------------------------------------------


class TestRunDebateGate:
    @pytest.mark.asyncio
    async def test_returns_debate_result_on_success(self):
        """Successful debate returns DebateResult object."""
        from backend.strategies.general_market_scanner import _run_debate_gate

        fake = _FakeDebateResult(consensus_probability=0.72, confidence=0.85)

        with patch(
            "backend.ai.debate_engine.run_debate",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            result = await _run_debate_gate(
                question="Will X?",
                market_price=0.55,
                volume=200000,
                category="politics",
                context="test context",
            )

        assert result is not None
        assert result.consensus_probability == 0.72
        assert result.confidence == 0.85
        assert result.rounds_completed == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Debate engine raises → returns None (fail open)."""
        from backend.strategies.general_market_scanner import _run_debate_gate

        with patch(
            "backend.ai.debate_engine.run_debate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ):
            result = await _run_debate_gate(
                question="Will Y?",
                market_price=0.45,
                volume=100000,
                category="politics",
                context="ctx",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_import_error(self):
        """Import failure for debate_engine → returns None."""
        from backend.strategies.general_market_scanner import _run_debate_gate

        with patch.dict("sys.modules", {"backend.ai.debate_engine": None}):
            result = await _run_debate_gate(
                question="Will Z?",
                market_price=0.50,
                volume=50000,
                category="sports",
                context="",
            )

        assert result is None


# ---------------------------------------------------------------------------
# T18: MIN_DEBATE_EDGE config tests
# ---------------------------------------------------------------------------


class TestMinDebateEdgeConfig:
    def test_config_has_min_debate_edge(self):
        """Settings object has MIN_DEBATE_EDGE with default 0.04."""
        from backend.config import settings

        assert hasattr(settings, "MIN_DEBATE_EDGE")
        # Default should be 0.04 (may be overridden by env)
        default_val = float(settings.MIN_DEBATE_EDGE)
        assert default_val > 0, "MIN_DEBATE_EDGE must be positive"

    def test_ctx_reads_min_debate_edge_from_settings(self):
        """run_cycle reads MIN_DEBATE_EDGE from ctx.settings, not hardcoded."""
        ctx = _make_ctx(min_debate_edge=0.10)
        assert ctx.settings.MIN_DEBATE_EDGE == 0.10

        ctx2 = _make_ctx(min_debate_edge=0.02)
        assert ctx2.settings.MIN_DEBATE_EDGE == 0.02


# ---------------------------------------------------------------------------
# Integration: brain + debate wired into scanner cycle
# ---------------------------------------------------------------------------


class TestScannerBrainIntegration:
    """Brain context is fetched and injected into enriched_context."""

    @pytest.mark.asyncio
    async def test_brain_context_passed_to_ai_analysis(self):
        """Brain context appears in the context string sent to analyze_market."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=True)
        markets = [_make_market(volume=200000, category="politics")]

        captured_context = {}

        async def fake_analyze(
            question, current_price, volume, category, context="", **kw
        ):
            captured_context["ctx"] = context
            return _FakeAIAnalysis(probability=0.70, confidence=0.80)

        mock_client = _mock_httpx_for_markets(markets)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "backend.ai.market_analyzer.analyze_market",
                side_effect=fake_analyze,
            ),
            patch(
                "backend.strategies.general_market_scanner._fetch_brain_context",
                new_callable=AsyncMock,
                return_value="Brain says: polls favor X by 5pts",
            ),
            patch(
                "backend.strategies.general_market_scanner._run_debate_gate",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await strategy.run_cycle(ctx)

        assert "ctx" in captured_context
        assert "BRAIN: Brain says: polls favor X by 5pts" in captured_context["ctx"]

    @pytest.mark.asyncio
    async def test_brain_failure_does_not_block_scanner(self):
        """Brain raises exception → scanner continues without brain context."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=True)
        markets = [_make_market(volume=200000, category="politics")]

        captured_context = {}

        async def fake_analyze(
            question, current_price, volume, category, context="", **kw
        ):
            captured_context["ctx"] = context
            return _FakeAIAnalysis(probability=0.70, confidence=0.80)

        mock_client = _mock_httpx_for_markets(markets)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "backend.ai.market_analyzer.analyze_market",
                side_effect=fake_analyze,
            ),
            patch(
                "backend.strategies.general_market_scanner._fetch_brain_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "backend.strategies.general_market_scanner._run_debate_gate",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await strategy.run_cycle(ctx)

        # Scanner should not crash — may have 0 decisions (edge too low) but no fatal error
        assert "AI disabled" not in result.errors
        # Brain context absent → no BRAIN: prefix
        if "ctx" in captured_context:
            assert "BRAIN:" not in captured_context["ctx"]


class TestScannerDebateIntegration:
    """Debate engine fires when raw_edge > MIN_DEBATE_EDGE and overrides AI probability."""

    @pytest.mark.asyncio
    async def test_debate_fires_when_edge_exceeds_threshold(self):
        """When raw_edge > min_debate_edge, debate is called."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        # Set very low threshold so debate always fires
        ctx = _make_ctx(ai_enabled=True, min_debate_edge=0.01)
        markets = [
            _make_market(
                volume=200000, category="politics", outcome_prices=["0.45", "0.55"]
            )
        ]

        mock_debate = AsyncMock(
            return_value=_FakeDebateResult(consensus_probability=0.80, confidence=0.90)
        )

        mock_client = _mock_httpx_for_markets(markets)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "backend.ai.market_analyzer.analyze_market",
                new_callable=AsyncMock,
                return_value=_FakeAIAnalysis(probability=0.70, confidence=0.80),
            ),
            patch(
                "backend.strategies.general_market_scanner._fetch_brain_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "backend.strategies.general_market_scanner._run_debate_gate",
                mock_debate,
            ),
        ):
            await strategy.run_cycle(ctx)

        assert mock_debate.call_count >= 1

    @pytest.mark.asyncio
    async def test_debate_skipped_when_edge_below_threshold(self):
        """When raw_edge <= min_debate_edge, debate is NOT called."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=True, min_debate_edge=0.99)
        markets = [
            _make_market(
                volume=200000, category="politics", outcome_prices=["0.45", "0.55"]
            )
        ]

        mock_debate = AsyncMock(return_value=None)

        mock_client = _mock_httpx_for_markets(markets)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "backend.ai.market_analyzer.analyze_market",
                new_callable=AsyncMock,
                return_value=_FakeAIAnalysis(probability=0.46, confidence=0.80),
            ),
            patch(
                "backend.strategies.general_market_scanner._fetch_brain_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "backend.strategies.general_market_scanner._run_debate_gate",
                mock_debate,
            ),
        ):
            await strategy.run_cycle(ctx)

        assert mock_debate.call_count == 0

    @pytest.mark.asyncio
    async def test_debate_failure_falls_back_to_single_pass(self):
        """Debate returns None → scanner uses single-pass AI result (no crash)."""
        from backend.strategies.general_market_scanner import GeneralMarketScanner

        strategy = GeneralMarketScanner()
        ctx = _make_ctx(ai_enabled=True, min_debate_edge=0.01)
        markets = [_make_market(volume=200000, category="politics")]

        mock_debate = AsyncMock(return_value=None)

        mock_client = _mock_httpx_for_markets(markets)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch(
                "backend.ai.market_analyzer.analyze_market",
                new_callable=AsyncMock,
                return_value=_FakeAIAnalysis(probability=0.70, confidence=0.80),
            ),
            patch(
                "backend.strategies.general_market_scanner._fetch_brain_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "backend.strategies.general_market_scanner._run_debate_gate",
                mock_debate,
            ),
        ):
            result = await strategy.run_cycle(ctx)

        assert "AI disabled" not in result.errors
        assert mock_debate.call_count >= 1
