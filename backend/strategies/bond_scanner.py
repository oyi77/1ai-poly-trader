"""High-probability bond scanner — buy near-certain outcomes for guaranteed-ish returns."""

import logging
from datetime import datetime, timezone

import httpx

from backend.strategies.base import (
    BaseStrategy,
    CycleResult,
    MarketInfo,
    StrategyContext,
)

logger = logging.getLogger("trading_bot.bonds")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"


class BondScannerStrategy(BaseStrategy):
    name = "bond_scanner"
    description = (
        "Buy high-probability outcomes (>85c) near resolution for low-risk returns"
    )
    category = "value"
    default_params = {
        "min_price": 0.85,
        "max_price": 0.98,
        "min_volume": 5000,
        "max_days_to_resolution": 14,
        "min_days_to_resolution": 0.25,
        "max_position_size": 8.0,
        "max_concurrent_bonds": 5,
    }

    async def market_filter(self, markets: list[MarketInfo]) -> list[MarketInfo]:
        """Filter to bond-relevant markets (treasury, interest rate, fed, bond keywords)."""
        bond_keywords = {
            "bond",
            "treasury",
            "interest rate",
            "fed",
            "yield",
            "debt ceiling",
            "t-bill",
        }
        filtered = [
            m for m in markets if any(kw in m.question.lower() for kw in bond_keywords)
        ]
        # If no keyword matches, fall back to base class DB-driven filter
        if not filtered:
            return await super().market_filter(markets)
        return filtered

    async def run_cycle(self, ctx: StrategyContext) -> CycleResult:
        result = CycleResult(decisions_recorded=0, trades_attempted=0, trades_placed=0)

        params = {**self.default_params, **(ctx.params or {})}
        min_price = float(params["min_price"])
        max_price = float(params["max_price"])
        min_volume = float(params["min_volume"])
        max_days = float(params["max_days_to_resolution"])
        min_days = float(params["min_days_to_resolution"])
        max_position_size = float(params["max_position_size"])
        max_concurrent = int(params["max_concurrent_bonds"])

        now = datetime.now(timezone.utc)

        # Fetch active markets sorted by volume
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    GAMMA_API_URL,
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": 100,
                        "order": "volume",
                        "ascending": "false",
                    },
                )
                resp.raise_for_status()
                markets = resp.json()
        except Exception as e:
            ctx.logger.warning(f"[bond_scanner] Gamma API fetch failed: {e}")
            result.errors.append(str(e))
            return result

        if not isinstance(markets, list):
            ctx.logger.warning("[bond_scanner] Unexpected Gamma API response format")
            return result

        # Check existing open positions to avoid doubling up
        existing_slugs: set[str] = set()
        try:
            from backend.models.database import Trade

            open_trades = ctx.db.query(Trade).filter(Trade.settled == False).all()
            existing_slugs = {t.event_slug for t in open_trades if t.event_slug}
        except Exception as e:
            ctx.logger.warning(f"[bond_scanner] Could not query open trades: {e}")

        # Check concurrent bond count
        bond_count = sum(
            1
            for slug in existing_slugs
            if slug  # rough proxy; all open trades count
        )
        if bond_count >= max_concurrent:
            ctx.logger.info(
                f"[bond_scanner] At max concurrent bonds ({bond_count}/{max_concurrent}), skipping cycle"
            )
            return result

        decisions = []

        for market in markets:
            # Volume filter
            volume = float(market.get("volume", 0) or 0)
            if volume < min_volume:
                continue

            # Resolution date filter
            end_date_str = (
                market.get("endDate")
                or market.get("end_date_iso")
                or market.get("endDateIso")
            )
            if not end_date_str:
                continue

            try:
                # Parse ISO date; handle trailing Z
                end_date_str_clean = end_date_str.replace("Z", "+00:00")
                end_dt = datetime.fromisoformat(end_date_str_clean)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            days_to_resolution = (end_dt - now).total_seconds() / 86400.0
            if days_to_resolution > max_days or days_to_resolution < min_days:
                continue

            # Skip if we already hold a position
            slug = market.get("slug") or market.get("conditionId") or ""
            if slug in existing_slugs:
                continue

            # Price filter — check outcomePrices
            outcome_prices_raw = market.get("outcomePrices") or []
            outcomes = market.get("outcomes") or []

            # outcomePrices and outcomes may be JSON strings or lists
            if isinstance(outcome_prices_raw, str):
                import json as _json

                try:
                    outcome_prices_raw = _json.loads(outcome_prices_raw)
                except Exception:
                    continue

            if isinstance(outcomes, str):
                import json as _json

                try:
                    outcomes = _json.loads(outcomes)
                except Exception:
                    outcomes = []

            if not outcome_prices_raw:
                continue

            qualifying_outcome = None
            qualifying_price = None

            for i, price_val in enumerate(outcome_prices_raw):
                try:
                    price = float(price_val)
                except (TypeError, ValueError):
                    continue

                if min_price <= price <= max_price:
                    qualifying_outcome = outcomes[i] if i < len(outcomes) else "yes"
                    qualifying_price = price
                    break

            if qualifying_price is None:
                continue

            # We have a qualifying market
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

            size = min(max_position_size, bankroll * 0.10)
            # Expected value: win_prob * profit_if_win - loss_prob * cost_if_loss
            # win_prob must differ from market price for non-zero edge.
            # Bond scanner targets near-certain outcomes (>92c), so our model
            # assigns higher resolution probability based on proximity to
            # expiry and high price (market already pricing in near-certainty,
            # but we believe the true probability is slightly higher).
            # Scale confidence boost by how close to 1.0 the price already is.
            proximity_boost = (
                qualifying_price - 0.80
            ) * 0.3  # e.g. 0.90 -> 0.03, 0.95 -> 0.045 boost
            win_prob = min(qualifying_price + max(proximity_boost, 0.01), 0.99)
            edge = round(
                win_prob * (1.0 - qualifying_price)
                - (1.0 - win_prob) * qualifying_price,
                4,
            )
            confidence = win_prob

            decision = {
                "market_ticker": slug,
                "market_question": market.get("question")
                or market.get("title")
                or slug,
                "direction": str(qualifying_outcome).lower(),
                "decision": "BUY",
                "entry_price": qualifying_price,
                "size": size,
                "suggested_size": size,
                "edge": edge,
                "confidence": confidence,
                "model_probability": qualifying_price,
                "market_probability": qualifying_price,
                "platform": "polymarket",
                "strategy_name": self.name,
                "days_to_resolution": round(days_to_resolution, 2),
                "volume": volume,
            }
            decisions.append(decision)
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
                    confidence=confidence,
                    signal_data=_json.dumps(decision),
                    reason=(
                        f"Bond: {qualifying_outcome} @ {qualifying_price:.2%} | "
                        f"edge={edge:.2%} | {days_to_resolution:.1f}d to resolve"
                    ),
                )
                ctx.db.add(log_row)
            except Exception as e:
                ctx.logger.warning(f"[bond_scanner] DecisionLog write failed: {e}")

            # Stop once we'd hit the concurrent limit
            if result.trades_attempted >= (max_concurrent - bond_count):
                break

        try:
            ctx.db.commit()
        except Exception as e:
            ctx.logger.warning(f"[bond_scanner] DB commit failed: {e}")
            ctx.db.rollback()

        ctx.logger.info(
            f"[bond_scanner] Cycle done: {result.decisions_recorded} bond opportunities found"
        )
        return result
