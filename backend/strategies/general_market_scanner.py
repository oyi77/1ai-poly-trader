"""General market scanner — finds edge across all Polymarket markets using AI analysis."""

import logging
from datetime import datetime, timezone

import httpx

from backend.strategies.base import BaseStrategy, CycleResult, StrategyContext

logger = logging.getLogger("trading_bot.general")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

SPORTS_KEYWORDS = frozenset(
    {
        "nba",
        "nfl",
        "mlb",
        "nhl",
        "epl",
        "ufc",
        "mls",
        "soccer",
        "football",
        "basketball",
        "baseball",
        "hockey",
        "tennis",
        "cricket",
        "boxing",
        "mma",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "champions league",
        "copa",
        "rugby",
        "f1",
        "formula 1",
        "grand prix",
    }
)


class GeneralMarketScanner(BaseStrategy):
    name = "general_scanner"
    description = "AI-powered scanner across all Polymarket markets — politics, sports, crypto, events"
    category = "ai_driven"
    default_params = {
        "min_volume": 2000,
        "min_edge": 0.03,
        "max_price": 0.85,
        "min_price": 0.08,
        "max_position_size": 2.0,
        "min_position_size": 0.30,
        "scan_limit": 500,
        "categories": "politics,crypto,science,culture",
        "max_ai_calls_per_cycle": 40,
        "max_concurrent": 25,
        "min_reward_risk": 0.3,
        "max_days_to_end": 30,
        "max_low_prob_size": 1.50,
        "low_prob_threshold": 0.20,
        "edge_dampening": 0.5,
        "sports_edge_multiplier": 3.0,
        # Max raw edge cap: reject if AI disagrees with market by more than this.
        # Tightened to 0.25 — a small model claiming 25%+ edge is almost always wrong.
        "max_raw_edge": 0.25,
        # Market anchor weight: blend AI prob toward market price.
        # final_prob = anchor_weight * market_price + (1-anchor_weight) * ai_prob
        # 0.7 = trust the market more than the AI.  An 8B model cannot reliably
        # beat liquid prediction markets — use it for slight tilts, not overrides.
        "market_anchor_weight": 0.7,
        # --- Safe harvesting strategy ---
        # Prefer NO bets on low-probability events.  Markets priced at YES 0.05-0.25
        # resolve NO >80% of the time.  Instead of trying to pick YES winners among
        # long-shots, harvest the NO side for steady 10-25% returns.
        # When True: for markets where YES < harvest_yes_ceiling, force direction=NO
        # unless AI strongly disagrees (raw_ai_prob > harvest_ai_override_threshold).
        "safe_harvest_enabled": True,
        "harvest_yes_ceiling": 0.25,  # Markets with YES below this → prefer NO
        "harvest_ai_override_threshold": 0.50,  # AI must be >50% YES to override harvest
        # --- Market-agree filter ---
        # Only trade when AI direction agrees with market lean.
        # If market says event is unlikely (YES < 0.40), only allow NO bets.
        # If market says event is likely (YES > 0.60), only allow YES bets.
        # In the 0.40-0.60 zone, allow either direction.
        "market_agree_enabled": True,
        "market_agree_low": 0.40,  # Below this: only NO trades allowed
        "market_agree_high": 0.60,  # Above this: only YES trades allowed
    }

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        result = CycleResult(decisions_recorded=0, trades_attempted=0, trades_placed=0)
        rejected_raw_edge = 0
        rejected_edge_low = 0
        rejected_rr = 0

        params = {**self.default_params, **(ctx.params or {})}
        min_volume = float(params["min_volume"])
        min_edge = float(params["min_edge"])
        max_price = float(params["max_price"])
        min_price = float(params["min_price"])
        max_position_size = float(params["max_position_size"])
        min_position_size = float(params.get("min_position_size", 0.50))
        scan_limit = int(params["scan_limit"])
        max_ai_calls_per_cycle = int(params.get("max_ai_calls_per_cycle", 40))
        max_concurrent = int(params.get("max_concurrent", 12))
        max_days_to_end = int(params.get("max_days_to_end", 30))
        max_low_prob_size = float(params.get("max_low_prob_size", 1.50))
        low_prob_threshold = float(params.get("low_prob_threshold", 0.20))
        edge_dampening = float(params.get("edge_dampening", 0.5))
        sports_edge_multiplier = float(params.get("sports_edge_multiplier", 3.0))
        max_raw_edge = float(params.get("max_raw_edge", 0.25))
        market_anchor_weight = float(params.get("market_anchor_weight", 0.7))
        safe_harvest_enabled = bool(params.get("safe_harvest_enabled", True))
        harvest_yes_ceiling = float(params.get("harvest_yes_ceiling", 0.25))
        harvest_ai_override = float(params.get("harvest_ai_override_threshold", 0.50))
        market_agree_enabled = bool(params.get("market_agree_enabled", True))
        market_agree_low = float(params.get("market_agree_low", 0.40))
        market_agree_high = float(params.get("market_agree_high", 0.60))
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
        open_trade_count = 0
        try:
            from backend.models.database import Trade

            open_trades = ctx.db.query(Trade).filter(Trade.settled == False).all()
            existing_tickers = {t.market_ticker for t in open_trades if t.market_ticker}
            open_trade_count = len(open_trades)
        except Exception:
            pass

        # Check concurrent trade limit
        if open_trade_count >= max_concurrent:
            ctx.logger.info(
                f"[general_scanner] At max concurrent trades ({open_trade_count}/{max_concurrent}), skipping cycle"
            )
            return result

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

            # End-date filter: skip markets that resolve too far in the future
            end_date_str = market.get("endDate") or ""
            if end_date_str:
                try:
                    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    days_until = (end_dt - datetime.now(timezone.utc)).days
                    if days_until > max_days_to_end:
                        continue
                except (ValueError, TypeError):
                    pass

            # In-loop concurrent check: stop placing if we hit the limit
            trades_placed_this_cycle = result.trades_placed
            if open_trade_count + trades_placed_this_cycle >= max_concurrent:
                ctx.logger.info(
                    f"[general_scanner] Hit max concurrent during cycle ({open_trade_count + trades_placed_this_cycle}/{max_concurrent}), stopping"
                )
                break

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

            # Market-anchor the AI probability: blend toward market consensus.
            # An 8B model should NOT override liquid market pricing by large amounts.
            raw_ai_prob = ai_prob
            ai_prob = (
                market_anchor_weight * market_price
                + (1.0 - market_anchor_weight) * raw_ai_prob
            )

            # Determine direction and edge
            if ai_prob > market_price:
                direction = "yes"
                edge = ai_prob - market_price
                entry_price = yes_price
            else:
                direction = "no"
                edge = market_price - ai_prob
                entry_price = no_price

            raw_edge = abs(raw_ai_prob - market_price)

            # Safe harvesting: for low-YES markets, force NO direction
            # unless the AI is VERY confident it will resolve YES.
            if safe_harvest_enabled and market_price < harvest_yes_ceiling:
                if raw_ai_prob < harvest_ai_override:
                    if direction == "yes":
                        ctx.logger.info(
                            f"[general_scanner] HARVEST: flipping {slug} from YES→NO "
                            f"(mkt={market_price:.3f} < ceiling={harvest_yes_ceiling}, "
                            f"ai_raw={raw_ai_prob:.3f} < override={harvest_ai_override})"
                        )
                        direction = "no"
                        entry_price = no_price
                        edge = market_price - ai_prob
                        if edge <= 0:
                            edge = (1.0 - market_price) * 0.05

            # Market-agree filter: only trade in the direction the market leans.
            if market_agree_enabled:
                if market_price < market_agree_low and direction == "yes":
                    ctx.logger.info(
                        f"[general_scanner] FILTER:MARKET_AGREE {slug}: "
                        f"market={market_price:.3f} < {market_agree_low} but AI says YES, rejecting"
                    )
                    rejected_edge_low += 1
                    continue
                if market_price > market_agree_high and direction == "no":
                    ctx.logger.info(
                        f"[general_scanner] FILTER:MARKET_AGREE {slug}: "
                        f"market={market_price:.3f} > {market_agree_high} but AI says NO, rejecting"
                    )
                    rejected_edge_low += 1
                    continue

            if raw_edge > max_raw_edge:
                ctx.logger.info(
                    f"[general_scanner] FILTER:RAW_EDGE {slug}: raw_edge={raw_edge:.4f} > max={max_raw_edge} "
                    f"(ai_raw={raw_ai_prob:.3f}, mkt={market_price:.3f})"
                )
                rejected_raw_edge += 1
                continue

            # Dampen the anchored edge further
            dampened_edge = edge * edge_dampening

            # Sports markets are hyper-efficient; require higher edge to trade
            q_lower = question.lower() if question else ""
            cats_lower = " ".join(market_categories)
            is_sports = (
                "sports" in market_categories
                or any(kw in q_lower for kw in SPORTS_KEYWORDS)
                or any(kw in cats_lower for kw in SPORTS_KEYWORDS)
            )
            required_edge = min_edge * sports_edge_multiplier if is_sports else min_edge

            if dampened_edge < required_edge:
                ctx.logger.info(
                    f"[general_scanner] FILTER:EDGE_LOW {slug}: dampened={dampened_edge:.4f} < required={required_edge:.4f}"
                    f" (raw={raw_edge:.4f}, anchored={edge:.4f}, dampen={edge_dampening}, sports={is_sports})"
                )
                rejected_edge_low += 1
                continue

            # R:R floor filter — reject trades where potential reward is too
            # low relative to risk.  For a binary bet the reward-to-risk is
            # (1/entry_price) - 1.  A floor of 0.5 means we need at least 50%
            # return potential (entry_price <= ~0.67).
            min_rr = float(params.get("min_reward_risk", 0.3))
            if entry_price > 0:
                reward_risk = (1.0 / entry_price) - 1.0
                if reward_risk < min_rr:
                    ctx.logger.info(
                        f"[general_scanner] FILTER:RR_LOW {slug}: R:R={reward_risk:.2f}x < min={min_rr}x (entry={entry_price:.4f})"
                    )
                    rejected_rr += 1
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
            size = max(min_position_size, size)

            if entry_price < low_prob_threshold:
                size = min(size, max_low_prob_size)

            category_caps = {
                "sports": 0.75,
                "politics": 1.50,
                "crypto": 2.00,
            }
            for cat_key, cap in category_caps.items():
                if cat_key in market_categories or (is_sports and cat_key == "sports"):
                    size = min(size, cap)
                    break

            reasoning = getattr(ai_result, "reasoning", "") or ""

            decision = {
                "market_ticker": slug,
                "market_question": question,
                "direction": direction,
                "decision": "BUY",
                "entry_price": entry_price,
                "size": size,
                "suggested_size": size,
                "edge": round(dampened_edge, 4),
                "raw_edge": round(raw_edge, 4),
                "confidence": getattr(ai_result, "confidence", 0.0),
                "model_probability": ai_prob,
                "raw_ai_probability": raw_ai_prob,
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
                        f"AI raw={raw_ai_prob:.2%} anchored={ai_prob:.2%} market={market_price:.2%} "
                        f"raw_edge={raw_edge:.2%} dampened={dampened_edge:.2%}"
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
            f"[general_scanner] Cycle done: {result.decisions_recorded} BUYs | "
            f"Rejected: raw_edge={rejected_raw_edge}, edge_low={rejected_edge_low}, rr_low={rejected_rr} | "
            f"AI calls={ai_calls_this_cycle}"
        )
        return result
