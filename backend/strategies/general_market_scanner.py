"""General market scanner — finds edge across all Polymarket markets using AI analysis."""

import logging
from datetime import datetime, timezone

import httpx

from backend.strategies.base import BaseStrategy, CycleResult, StrategyContext

logger = logging.getLogger("trading_bot.general")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"


class GeneralMarketScanner(BaseStrategy):
    name = "general_scanner"
    description = "AI-powered scanner across all Polymarket markets — politics, sports, crypto, events"
    category = "ai_driven"
    default_params = {
        "min_volume": 10000,
        "min_edge": 0.08,
        "max_price": 0.75,
        "min_price": 0.15,
        "max_position_size": 8.0,
        "scan_limit": 40,
        "categories": "politics,sports,crypto,science,culture",
        "max_ai_calls_per_cycle": 8,
    }

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        result = CycleResult(decisions_recorded=0, trades_attempted=0, trades_placed=0)

        params = {**self.default_params, **(ctx.params or {})}
        min_volume = float(params["min_volume"])
        min_edge = float(params["min_edge"])
        max_price = float(params["max_price"])
        min_price = float(params["min_price"])
        max_position_size = float(params["max_position_size"])
        scan_limit = int(params["scan_limit"])
        max_ai_calls_per_cycle = int(params.get("max_ai_calls_per_cycle", 5))
        allowed_categories_raw = params.get("categories", "")
        allowed_categories = {
            c.strip().lower()
            for c in str(allowed_categories_raw).split(",")
            if c.strip()
        }

        # AI is required for this strategy to have any edge
        if not ctx.settings.AI_ENABLED:
            ctx.logger.info(
                "[general_scanner] AI disabled — skipping cycle (AI required for edge)"
            )
            result.errors.append("AI disabled")
            return result

        # Fetch top markets by volume
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    GAMMA_API_URL,
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": scan_limit,
                        "order": "volume",
                        "ascending": "false",
                    },
                )
                resp.raise_for_status()
                markets = resp.json()
        except Exception as e:
            ctx.logger.warning(f"[general_scanner] Gamma API fetch failed: {e}")
            result.errors.append(str(e))
            return result

        if not isinstance(markets, list):
            ctx.logger.warning("[general_scanner] Unexpected Gamma API response format")
            return result

        # Load AI analyzer
        try:
            from backend.ai.market_analyzer import analyze_market
        except ImportError as e:
            ctx.logger.warning(
                f"[general_scanner] AI market_analyzer not available: {e}"
            )
            result.errors.append(f"AI module unavailable: {e}")
            return result

        # Fetch current bankroll
        bankroll = 100.0
        try:
            from backend.models.database import BotState
            from backend.config import settings as _settings

            state = ctx.db.query(BotState).first()
            if state:
                bankroll = (
                    float(state.bankroll)
                    if _settings.TRADING_MODE != "paper"
                    else float(state.paper_bankroll or state.bankroll)
                )
        except Exception:
            pass

        ai_calls_this_cycle = 0
        existing_tickers: set = set()
        try:
            from backend.models.database import Trade

            open_trades = ctx.db.query(Trade).filter(Trade.settled == False).all()
            existing_tickers = {t.market_ticker for t in open_trades if t.market_ticker}
        except Exception:
            pass

        for market in markets:
            # Volume filter
            volume = float(market.get("volume", 0) or 0)
            if volume < min_volume:
                continue

            # Category filter — skip when API returns null/empty categories
            category_raw = market.get("category") or market.get("tags") or ""
            if isinstance(category_raw, list):
                market_categories = {str(c).lower().strip() for c in category_raw if c}
            else:
                cat_str = str(category_raw).lower().strip()
                market_categories = {cat_str} if cat_str else set()

            # Only apply category filter if the market actually HAS category data
            # Gamma API often returns category=null, so pass those through to AI
            if (
                market_categories
                and allowed_categories
                and not (market_categories & allowed_categories)
            ):
                # Try substring match on question text as fallback
                question = market.get("question", "").lower()
                combined = " ".join(market_categories) + " " + question
                if not any(cat in combined for cat in allowed_categories):
                    continue

            # Extract YES price (first outcome price)
            outcome_prices_raw = market.get("outcomePrices") or []
            if isinstance(outcome_prices_raw, str):
                import json as _json

                try:
                    outcome_prices_raw = _json.loads(outcome_prices_raw)
                except Exception:
                    continue

            if not outcome_prices_raw:
                continue

            try:
                yes_price = float(outcome_prices_raw[0])
            except (TypeError, ValueError, IndexError):
                continue

            no_price = 1.0 - yes_price

            # Price range filter (both sides)
            if yes_price < min_price or yes_price > max_price:
                # Check NO side
                if no_price < min_price or no_price > max_price:
                    continue

            slug = market.get("slug") or market.get("conditionId") or ""

            # Skip markets we already have an open trade on
            if slug and slug in existing_tickers:
                continue

            question = market.get("question") or market.get("title") or slug

            # AI analysis — enforce per-cycle call cap
            if ai_calls_this_cycle >= max_ai_calls_per_cycle:
                ctx.logger.debug(
                    f"AI call cap reached ({max_ai_calls_per_cycle}), using technical signals for remaining markets"
                )
                continue

            try:
                ai_result = await analyze_market(
                    question=question,
                    current_price=yes_price,
                    volume=volume,
                    category=next(iter(market_categories), "general"),
                )
            except Exception as e:
                ctx.logger.debug(
                    f"[general_scanner] AI analysis failed for {slug}: {e}"
                )
                continue

            ai_calls_this_cycle += 1

            if not ai_result:
                continue

            ai_prob = float(ai_result.probability)
            market_price = yes_price

            # Determine direction and edge
            if ai_prob > market_price:
                direction = "yes"
                edge = ai_prob - market_price
                entry_price = yes_price
            else:
                direction = "no"
                edge = market_price - ai_prob
                entry_price = no_price

            # Edge filter
            if edge < min_edge:
                continue

            # Kelly criterion sizing (fractional)
            kelly_fraction = ctx.settings.KELLY_FRACTION
            if entry_price > 0 and entry_price < 1:
                b = (1.0 - entry_price) / entry_price  # net odds
                q = 1.0 - ai_prob
                kelly_full = (ai_prob * b - q) / b
                kelly_size = max(0.0, kelly_full * kelly_fraction * bankroll)
            else:
                kelly_size = max_position_size

            size = min(max_position_size, kelly_size)
            size = max(1.0, size)  # at least $1

            reasoning = getattr(ai_result, "reasoning", "") or ""

            decision = {
                "market_ticker": slug,
                "market_question": question,
                "direction": direction,
                "decision": "BUY",
                "entry_price": entry_price,
                "size": size,
                "suggested_size": size,
                "edge": round(edge, 4),
                "confidence": getattr(ai_result, "confidence", 0.0),
                "model_probability": ai_prob,
                "market_probability": market_price,
                "platform": "polymarket",
                "strategy_name": self.name,
                "volume": volume,
                "reasoning": reasoning,
            }

            result.decisions.append(decision)
            result.decisions_recorded += 1
            result.trades_attempted += 1

            # Log decision
            try:
                from backend.models.database import DecisionLog
                import json as _json

                log_row = DecisionLog(
                    strategy=self.name,
                    market_ticker=slug[:64] if slug else "unknown",
                    decision="BUY",
                    confidence=getattr(ai_result, "confidence", None),
                    signal_data=_json.dumps(
                        {k: v for k, v in decision.items() if k != "reasoning"}
                    ),
                    reason=(
                        f"AI edge: {direction.upper()} @ {entry_price:.2%} | "
                        f"AI prob={ai_prob:.2%} market={market_price:.2%} edge={edge:.2%}"
                    ),
                )
                ctx.db.add(log_row)
            except Exception as e:
                ctx.logger.warning(f"[general_scanner] DecisionLog write failed: {e}")

        try:
            ctx.db.commit()
        except Exception as e:
            ctx.logger.warning(f"[general_scanner] DB commit failed: {e}")
            ctx.db.rollback()

        ctx.logger.info(
            f"[general_scanner] Cycle done: {result.decisions_recorded} opportunities found"
        )
        return result
