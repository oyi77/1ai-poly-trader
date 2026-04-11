"""Settlement helper functions - API resolution, P&L calculation, weather calibration."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

import httpx
from cachetools import TTLCache

from backend.models.database import Trade, Signal, SettlementEvent, TradeContext

logger = logging.getLogger("trading_bot")

# Module-level: track consecutive 404s per market_id (bounded TTLCache: 1000 entries, 1 hour TTL)
_market_404_counts: TTLCache = TTLCache(maxsize=1000, ttl=3600)


async def fetch_polymarket_resolution(
    market_id: str, event_slug: Optional[str] = None
) -> Tuple[bool, Optional[float]]:
    """
    Fetch actual market resolution from Polymarket API.

    For BTC 5-min markets, uses event slug to find the market.

    Returns: (is_resolved, settlement_value)
        - settlement_value: 1.0 if Up won, 0.0 if Down won
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try event slug first (more reliable for BTC 5-min markets)
            if event_slug:
                response = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={"slug": event_slug},
                )
                response.raise_for_status()
                events = response.json()

                if events:
                    event = events[0] if isinstance(events, list) else events
                    markets = event.get("markets", [])
                    if markets:
                        return _parse_market_resolution(markets[0])

            # Try slug-based query first (market_id may be a slug, not numeric ID)
            slug_response = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"slug": market_id},
            )
            if slug_response.status_code == 200:
                slug_results = slug_response.json()
                if isinstance(slug_results, list) and slug_results:
                    return _parse_market_resolution(slug_results[0])

            # Fallback: try market ID directly (works for numeric IDs)
            url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            response = await client.get(url)

            if response.status_code in (404, 422):
                _market_404_counts[market_id] = _market_404_counts.get(market_id, 0) + 1
                if _market_404_counts[market_id] >= 3:
                    logger.debug(
                        f"Skipping market {market_id} — 3+ consecutive 404/422s"
                    )
                    return False, None
                return await _search_market_in_events(market_id)

            response.raise_for_status()
            market = response.json()
            return _parse_market_resolution(market)

    except Exception as e:
        logger.warning(
            f"[settlement_helpers.fetch_polymarket_resolution] {type(e).__name__}: Failed to fetch resolution for {event_slug or market_id}: {e}"
        )
        return False, None


async def _search_market_in_events(market_id: str) -> Tuple[bool, Optional[float]]:
    """Search for market in events (both active and closed)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for closed in [True, False]:
                params = {"closed": str(closed).lower(), "limit": 200}
                response = await client.get(
                    "https://gamma-api.polymarket.com/events", params=params
                )
                response.raise_for_status()
                events = response.json()

                for event in events:
                    for market in event.get("markets", []):
                        if str(market.get("id")) == str(market_id):
                            return _parse_market_resolution(market)

        return False, None

    except Exception as e:
        logger.warning(
            f"[settlement_helpers._search_market_in_events] {type(e).__name__}: Failed to search for market {market_id}: {e}"
        )
        return False, None


def _parse_market_resolution(market: dict) -> Tuple[bool, Optional[float]]:
    """
    Parse market data to determine if resolved and outcome.

    Handles both Yes/No and Up/Down outcomes.
    - outcomePrices[0] > 0.99 -> first outcome won (Yes or Up)
    - outcomePrices[0] < 0.01 -> second outcome won (No or Down)

    Also supports early resolution heuristic: if the market is not yet
    officially closed but prices are extreme AND the event appears to have
    concluded, treat it as resolved so we don't wait hours for Polymarket
    to flip the closed flag.
    """
    is_closed = market.get("closed", False)

    outcome_prices = market.get("outcomePrices", [])
    if not outcome_prices:
        return False, None

    try:
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)

        first_price = float(outcome_prices[0]) if outcome_prices else 0.5

        # --- Officially closed: use tight thresholds (existing logic) ---
        if is_closed:
            if first_price > 0.99:
                logger.info(f"Market {market.get('id')} resolved: UP/YES won")
                return True, 1.0
            elif first_price < 0.01:
                logger.info(f"Market {market.get('id')} resolved: DOWN/NO won")
                return True, 0.0
            else:
                return False, None

        # --- Early resolution heuristic (market not yet closed) ---
        # Only trigger when prices are very extreme (>0.97 or <0.03) AND
        # there is external evidence that the event has concluded.
        if first_price > 0.97 or first_price < 0.03:
            event_concluded = _check_event_concluded(market)
            if event_concluded:
                if first_price > 0.97:
                    logger.info(
                        f"Market {market.get('id')} early-resolved (price={first_price:.3f}, "
                        f"event concluded): UP/YES won"
                    )
                    return True, 1.0
                else:
                    logger.info(
                        f"Market {market.get('id')} early-resolved (price={first_price:.3f}, "
                        f"event concluded): DOWN/NO won"
                    )
                    return True, 0.0

        return False, None

    except (ValueError, IndexError, TypeError) as e:
        logger.warning(f"Failed to parse outcome prices: {e}")
        return False, None


def _check_event_concluded(market: dict) -> bool:
    """
    Determine whether the underlying event has concluded, even if Polymarket
    hasn't set closed=True yet.

    For sports markets: checks ``events[0].ended`` flag.
    For non-sports:     checks whether ``endDate`` has passed by ≥2 hours.
    """
    now = datetime.now(timezone.utc)

    # Sports markets: the Gamma API sets events[0].ended = True once the
    # match finishes, well before the market is officially closed.
    events = market.get("events", [])
    if events and isinstance(events, list):
        event = events[0] if isinstance(events[0], dict) else {}
        if event.get("ended") is True:
            return True
        # If the game is still live, definitely not concluded.
        if event.get("live") is True and event.get("ended") is not True:
            return False

    # Non-sports / fallback: use endDate.  For non-sports markets endDate is
    # the resolution deadline.  We require it to have passed by ≥2 hours to
    # avoid premature settlement on pre-event price spikes.
    end_date_str = market.get("endDate")
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            if now >= end_date + timedelta(hours=2):
                return True
        except (ValueError, TypeError):
            pass

    return False


async def _fetch_kalshi_resolution(ticker: str) -> Tuple[bool, Optional[float]]:
    """Fetch resolution status for a Kalshi market."""
    try:
        from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present

        if not kalshi_credentials_present():
            return False, None

        client = KalshiClient()
        data = await client.get_market(ticker)
        market = data.get("market", data)

        status = market.get("status", "")
        result = market.get("result", "")

        if status in ("finalized", "determined") and result:
            if result == "yes":
                return True, 1.0
            elif result == "no":
                return True, 0.0

        return False, None

    except Exception as e:
        logger.warning(
            f"[settlement_helpers._fetch_kalshi_resolution] {type(e).__name__}: Failed to fetch Kalshi resolution for {ticker}: {e}"
        )
        return False, None


def calculate_pnl(trade: Trade, settlement_value: float) -> float:
    """
    Calculate P&L for a trade given the settlement value.

    settlement_value: 1.0 if Up/Yes outcome, 0.0 if Down/No outcome

    Maps up->yes, down->no internally:
    - UP position wins when settlement = 1.0
    - DOWN position wins when settlement = 0.0

    IMPORTANT: `size` is the dollar amount spent (not number of shares).
    Number of shares = size / entry_price.
    On a win, each share pays $1.00, so PNL = shares - cost = (size / entry_price) - size.
    On a loss, the entire investment is lost, so PNL = -size.
    """
    # Map up/down to yes/no logic
    direction = trade.direction
    if direction == "up":
        direction = "yes"
    elif direction == "down":
        direction = "no"

    _filled = getattr(trade, "filled_size", None)
    size = float(_filled) if isinstance(_filled, (int, float)) else trade.size

    entry_price = trade.entry_price

    if not entry_price or entry_price <= 0 or entry_price >= 1.0:
        if entry_price and entry_price >= 1.0:
            return 0.0
        if direction == "yes":
            return round(size if settlement_value == 1.0 else -size, 2)
        else:
            return round(size if settlement_value == 0.0 else -size, 2)

    # PNL formula: shares = dollars_spent / price_per_share
    # Win: pnl = shares * $1 - cost = (size / entry_price) - size
    # Loss: pnl = -size (entire investment lost)
    if direction == "yes":
        if settlement_value == 1.0:
            pnl = (size / entry_price) - size
        else:
            pnl = -size
    else:
        if settlement_value == 0.0:
            pnl = (size / entry_price) - size
        else:
            pnl = -size

    return round(pnl, 2)


async def check_market_settlement(
    trade: Trade,
) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Check if a trade's market has settled.

    Returns: (is_settled, settlement_value, pnl)
    """
    is_resolved, settlement_value = await fetch_polymarket_resolution(
        trade.market_ticker, event_slug=trade.event_slug
    )

    if not is_resolved or settlement_value is None:
        return False, None, None

    pnl = calculate_pnl(trade, settlement_value)

    mapped_dir = "UP" if trade.direction in ("up", "yes") else "DOWN"
    outcome = "UP" if settlement_value == 1.0 else "DOWN"
    result = "WIN" if mapped_dir == outcome else "LOSS"

    logger.info(
        f"Trade {trade.id} settled: {mapped_dir} @ {trade.entry_price:.0%} -> "
        f"{result} P&L: ${pnl:+.2f}"
    )

    return True, settlement_value, pnl


async def check_weather_settlement(
    trade: Trade,
) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Check if a weather trade's market has settled.
    Routes to the correct platform's resolution method.
    """
    platform = getattr(trade, "platform", "polymarket") or "polymarket"

    if platform == "kalshi":
        is_resolved, settlement_value = await _fetch_kalshi_resolution(
            trade.market_ticker
        )
    else:
        is_resolved, settlement_value = await fetch_polymarket_resolution(
            trade.market_ticker,
            event_slug=trade.event_slug,
        )

    if is_resolved and settlement_value is not None:
        pnl = calculate_pnl(trade, settlement_value)
        return True, settlement_value, pnl

    return False, None, None


async def _resolve_markets(
    normal_tickers: set,
    weather_tickers: set,
    trade_slugs: dict,
    trade_platforms: dict,
) -> dict:
    """
    Resolve all unique market tickers concurrently.

    Returns a dict mapping ticker -> (is_resolved, settlement_value).
    normal_tickers: set of tickers for BTC/standard markets.
    weather_tickers: set of tickers for weather markets.
    trade_slugs: dict mapping ticker -> event_slug (may be None).
    trade_platforms: dict mapping ticker -> platform string.
    """

    async def _resolve_one(ticker: str, is_weather: bool):
        platform = trade_platforms.get(ticker, "polymarket") or "polymarket"
        if is_weather and platform == "kalshi":
            result = await _fetch_kalshi_resolution(ticker)
        else:
            result = await fetch_polymarket_resolution(
                ticker, event_slug=trade_slugs.get(ticker)
            )
        return ticker, result

    tasks = [_resolve_one(t, False) for t in normal_tickers] + [
        _resolve_one(t, True) for t in weather_tickers
    ]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    resolutions = {}
    for item in gathered:
        if isinstance(item, Exception):
            logger.error(f"Market resolution error: {item}")
            continue
        ticker, result = item
        resolutions[ticker] = result
    return resolutions


async def _get_actual_temp_from_openmeteo(
    city_key: str, target_date: str
) -> Optional[float]:
    try:
        from backend.data.weather import CITY_CONFIG

        cfg = CITY_CONFIG.get(city_key, {})
        lat = cfg.get("lat")
        lon = cfg.get("lon")
        if not lat or not lon:
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": target_date,
                    "end_date": target_date,
                    "daily": "temperature_2m_max"
                    if cfg.get("metric") != "low"
                    else "temperature_2m_min",
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            daily = data.get("daily", {})
            temps = daily.get("temperature_2m_max") or daily.get("temperature_2m_min")
            if temps and len(temps) > 0:
                return float(temps[0])
    except Exception as e:
        logger.debug(
            f"[settlement_helpers._get_actual_temp_from_openmeteo] {type(e).__name__}: {e}"
        )
    return None


async def _try_calibrate_weather(signal, settlement_value: float) -> None:
    try:
        from backend.core.calibration import update_calibration

        sources = signal.sources or []
        city_key = next(
            (s.split(":", 1)[1] for s in sources if s.startswith("city:")),
            None,
        )
        if not city_key:
            return

        m = re.search(r"Ensemble:\s*([\d.]+)F", signal.reasoning or "")
        if not m:
            return
        forecast_temp_f = float(m.group(1))

        m2 = re.search(r"(?:above|below)\s*([\d.]+)F", signal.reasoning)
        threshold_f = float(m2.group(1)) if m2 else forecast_temp_f

        target_date_match = re.search(
            r"on\s+(\d{4}-\d{2}-\d{2})", signal.reasoning or ""
        )
        actual_temp_f = None

        if target_date_match:
            target_date = target_date_match.group(1)
            actual_temp_f = await _get_actual_temp_from_openmeteo(city_key, target_date)

        if actual_temp_f is None:
            direction_above = "above" in (signal.reasoning or "").lower().split("|")[0]
            if settlement_value == 1.0:
                actual_temp_f = (
                    threshold_f + 1.0 if direction_above else threshold_f - 1.0
                )
            else:
                actual_temp_f = (
                    threshold_f - 1.0 if direction_above else threshold_f + 1.0
                )

        update_calibration(
            city_key,
            source="gefs",
            forecast_temp_f=forecast_temp_f,
            actual_temp_f=actual_temp_f,
        )
        logger.debug(
            f"Calibration updated: {city_key} forecast={forecast_temp_f:.1f} actual≈{actual_temp_f:.1f}"
        )

    except Exception as e:
        logger.debug(
            f"[settlement_helpers._try_calibrate_weather] {type(e).__name__}: Calibration update skipped (best-effort): {e}"
        )


async def _record_weather_observation(trade, settlement_value: float, db) -> None:
    from backend.strategies.weather_emos import (
        load_calibration_states,
        save_calibration_states,
        CalibrationState,
    )

    signal_data = getattr(trade, "signal_data", None)
    if not signal_data:
        try:
            ctx = (
                db.query(TradeContext).filter(TradeContext.trade_id == trade.id).first()
            )
            if ctx and ctx.signal_source:
                try:
                    signal_data = json.loads(ctx.signal_source)
                except Exception as e:
                    logger.debug(
                        f"[settlement_helpers._record_weather_observation] {type(e).__name__}: JSON parse of signal_source failed: {e}"
                    )
        except Exception as e:
            logger.debug(
                f"[settlement_helpers._record_weather_observation] {type(e).__name__}: DB query for TradeContext failed: {e}"
            )

    if not signal_data:
        logger.debug(f"Weather calibration: no signal_data for trade {trade.id}")
        return

    if isinstance(signal_data, str):
        try:
            signal_data = json.loads(signal_data)
        except Exception as e:
            logger.debug(
                f"[settlement_helpers._record_weather_observation] {type(e).__name__}: could not parse signal_data for trade {trade.id}: {e}"
            )
            return

    forecast_mean_f = signal_data.get("forecast_mean_f") or signal_data.get(
        "forecast_temp"
    )
    calibrated_std_f = signal_data.get("calibrated_std_f", 5.0)
    city = signal_data.get("city")
    direction = signal_data.get("direction", "above")
    threshold_f = signal_data.get("threshold_f")

    if not forecast_mean_f or not city:
        logger.debug(
            f"Weather calibration: missing forecast_mean_f or city for trade {trade.id}"
        )
        return

    if threshold_f:
        if settlement_value == 1.0:
            if direction == "above":
                actual_temp_f = threshold_f + 2.0
            else:
                actual_temp_f = threshold_f - 2.0
        else:
            if direction == "above":
                actual_temp_f = threshold_f - 2.0
            else:
                actual_temp_f = threshold_f + 2.0
    else:
        actual_temp_f = forecast_mean_f + (2.0 if settlement_value == 1.0 else -2.0)

    cal_states = load_calibration_states(db, "weather_emos")
    cal = cal_states.get(city, CalibrationState())
    cal.add_observation(forecast_mean_f, calibrated_std_f, actual_temp_f)
    cal_states[city] = cal
    save_calibration_states(db, "weather_emos", cal_states)
    logger.info(
        f"Weather EMOS: recorded obs for {city}: forecast={forecast_mean_f:.1f}F actual~{actual_temp_f:.1f}F"
    )


async def process_settled_trade(
    trade: Trade,
    is_settled: bool,
    settlement_value: Optional[float],
    pnl: Optional[float],
    db: Session,
) -> bool:
    """
    Process a settled trade - update trade record, broadcast event, create settlement event,
    backfill decision log, and update signal.

    Returns True if trade was successfully processed and added to settled_trades list.
    """
    if not is_settled or settlement_value is None:
        return False

    trade.settled = True
    trade.settlement_value = settlement_value
    trade.pnl = pnl
    trade.settlement_time = datetime.now(timezone.utc)
    if pnl is not None and pnl > 0:
        trade.result = "win"
    elif pnl is not None and pnl < 0:
        trade.result = "loss"
    else:
        trade.result = "push"

    # Broadcast event
    try:
        from backend.core.event_bus import _broadcast_event

        _broadcast_event(
            "trade_settled",
            {
                "trade_id": trade.id,
                "market_ticker": trade.market_ticker,
                "result": trade.result,
                "pnl": trade.pnl,
                "mode": getattr(trade, "trading_mode", "paper"),
            },
        )
    except Exception as e:
        logger.debug(
            f"[settlement_helpers.process_settled_trade] {type(e).__name__}: broadcast event failed: {e}"
        )

    # Create settlement event
    platform = getattr(trade, "platform", "polymarket") or "polymarket"
    resolved_outcome = "up" if settlement_value == 1.0 else "down"
    db.add(
        SettlementEvent(
            trade_id=trade.id,
            market_ticker=trade.market_ticker,
            resolved_outcome=resolved_outcome,
            pnl=pnl,
            source=platform,
        )
    )

    # Backfill DecisionLog outcome for this trade
    try:
        from backend.models.database import DecisionLog

        outcome = (
            "WIN"
            if trade.result == "win"
            else ("LOSS" if trade.result == "loss" else "PUSH")
        )
        # Try to get strategy from TradeContext
        trade_ctx = (
            db.query(TradeContext).filter(TradeContext.trade_id == trade.id).first()
        )
        dl_query = db.query(DecisionLog).filter(
            DecisionLog.market_ticker == trade.market_ticker,
            DecisionLog.outcome == None,
            DecisionLog.decision == "BUY",
        )
        if trade_ctx and trade_ctx.strategy:
            dl_query = dl_query.filter(DecisionLog.strategy == trade_ctx.strategy)
        decisions = dl_query.all()
        for decision in decisions:
            decision.outcome = outcome
    except Exception as e:
        logger.debug(
            f"[settlement_helpers.process_settled_trade] {type(e).__name__}: DecisionLog outcome backfill failed for {trade.market_ticker}: {e}"
        )

    # Update linked signal
    if trade.signal_id:
        linked_signal = db.query(Signal).filter(Signal.id == trade.signal_id).first()
        if linked_signal:
            actual_outcome = "up" if settlement_value == 1.0 else "down"
            linked_signal.actual_outcome = actual_outcome
            linked_signal.outcome_correct = linked_signal.direction == actual_outcome
            linked_signal.settlement_value = settlement_value
            linked_signal.settled_at = datetime.now(timezone.utc)
            market_type = getattr(trade, "market_type", "btc") or "btc"
            if market_type == "weather" and linked_signal.sources:
                await _try_calibrate_weather(linked_signal, settlement_value)

            if market_type == "weather":
                try:
                    await _record_weather_observation(trade, settlement_value, db)
                except Exception as e:
                    logger.debug(
                        f"[settlement_helpers.process_settled_trade] {type(e).__name__}: Weather calibration update skipped: {e}"
                    )

    # Write outcome to BigBrain (unified memory)
    try:
        from backend.clients.bigbrain import get_bigbrain

        brain = get_bigbrain()
        await brain.write_trade_outcome(
            {
                "strategy": getattr(trade, "strategy", "unknown"),
                "market": trade.market_ticker,
                "direction": trade.direction,
                "result": trade.result,
                "pnl": pnl,
                "edge": getattr(trade, "edge_at_entry", 0.0),
                "confidence": getattr(trade, "confidence", 0.5),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.debug(
            f"[settlement_helpers.process_settled_trade] {type(e).__name__}: BigBrain write_trade_outcome failed: {e}"
        )

    return True
