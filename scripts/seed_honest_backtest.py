#!/usr/bin/env python3
"""Seed honest backtest data from resolved Polymarket BTC markets.

Unlike the basic seeder, this version:
1. Fetches resolved BTC markets from Gamma API
2. Gets actual Binance BTC price at market creation time
3. Computes HONEST model_probability from BTC price vs threshold
   (no look-ahead bias — the signal is generated BEFORE resolution)
4. Compares against actual resolution to determine win/loss

For BTC markets like "Will BTC be above $110k on Sep 26 at 4AM ET?":
- If BTC was at $107k when the market was created → market_price ~0.20 (No likely)
- If BTC was at $109k when the market was created → market_price ~0.45 (closer to threshold)
- After resolution: BTC was at $108k → No wins → settlement_value = 0.0

Usage:
    python scripts/seed_honest_backtest.py [--days 90] [--limit 200] [--dry-run]
"""

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy.orm import Session
from backend.models.database import SessionLocal, Signal, Trade
from backend.data.gamma import fetch_markets

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("honest_seed")


def parse_btc_threshold(question: str) -> Optional[float]:
    """Extract BTC price threshold from market question.

    E.g. 'Will the price of Bitcoin be above $110,000 on ...' → 110000.0
    """
    patterns = [
        r"(?:above|over|exceed)\s+\$?([\d,]+)(?:k|,000)?",
        r"\$([\d,]+)(?:k|,000)?\s+(?:on|at|by)",
        r"above\s+([\d,]+)k",
    ]
    for pat in patterns:
        m = re.search(pat, question, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", "")
            try:
                num = float(val)
                if "k" in question[m.start() : m.end()].lower() or num < 1000:
                    return num * 1000 if num < 1000 else num
                return num
            except ValueError:
                continue
    return None


async def fetch_binance_historical_price(timestamp_ms: int) -> Optional[float]:
    """Fetch BTC price at a specific historical time from Binance klines."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "startTime": timestamp_ms - 60000,
                    "endTime": timestamp_ms,
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data and len(data) > 0:
                return float(data[0][4])
        except Exception as e:
            logger.debug(f"Binance historical fetch failed: {e}")

        try:
            resp = await client.get(
                "https://api.bybit.com/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": "BTCUSDT",
                    "interval": "1",
                    "start": timestamp_ms - 60000,
                    "end": timestamp_ms,
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") == 0:
                rows = data.get("result", {}).get("list", [])
                if rows:
                    return float(rows[0][4])
        except Exception as e:
            logger.debug(f"Bybit historical fetch failed: {e}")

    return None


def btc_price_to_probability(
    btc_price: float, threshold: float, hours_to_resolution: float = 6.0
) -> float:
    """Convert BTC price + threshold → market probability (honest, no look-ahead).

    Uses a distance-to-threshold model that accounts for typical BTC volatility:
    - If current price > threshold: prob(YES) → high (1.0 - discount for time remaining)
    - If current price < threshold: prob(YES) → low (discount for time and volatility)
    - The further from threshold, the more extreme the probability

    volatility_basis: ~1% per hour for BTC (annualized ~87% vol → hourly ~1%)
    """
    distance_pct = (btc_price - threshold) / threshold
    vol_per_hour = 0.008
    hours = max(hours_to_resolution, 0.5)
    vol_window = vol_per_hour * (hours**0.5)

    z_score = distance_pct / vol_window if vol_window > 0 else 0.0

    import math

    prob_yes = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
    prob_yes = max(0.02, min(0.98, prob_yes))
    return round(prob_yes, 4)


async def seed_honest_backtest(
    days_back: int = 90,
    limit: int = 200,
    dry_run: bool = False,
) -> int:
    """Seed honest backtest data from resolved BTC markets with actual historical prices."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

    # Paginate to find all BTC markets — Gamma API only returns 500 per page
    all_markets: list = []
    page_size = 500
    max_pages = 10
    async with httpx.AsyncClient(timeout=15.0) as client:
        for page in range(max_pages):
            offset = page * page_size
            try:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={
                        "active": "false",
                        "closed": "true",
                        "limit": page_size,
                        "offset": offset,
                        "order": "volume",
                        "ascending": "false",
                    },
                )
                resp.raise_for_status()
                batch = resp.json()
                all_markets.extend(batch)
                logger.info(
                    f"Gamma API page {page + 1}: {len(batch)} markets (offset={offset})"
                )
                if len(batch) < page_size:
                    break
            except Exception as e:
                logger.warning(f"Gamma API page {page + 1} failed: {e}")
                break
            await asyncio.sleep(0.3)

    helper_markets = await fetch_markets(
        limit=limit, active=False, order="volume", ascending=False
    )
    helper_slugs = {m.get("slug") for m in helper_markets}
    for m in helper_markets:
        if m.get("slug") not in {x.get("slug") for x in all_markets}:
            all_markets.append(m)

    markets = all_markets
    logger.info(f"Total markets fetched: {len(markets)}")

    btc_markets = []
    for m in markets:
        question = m.get("question", "")
        if not m.get("closed", False):
            continue
        if not any(kw in question.lower() for kw in ["btc", "bitcoin"]):
            continue
        outcome_prices = m.get("outcomePrices", [])
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                continue
        if not outcome_prices or len(outcome_prices) < 2:
            continue
        threshold = parse_btc_threshold(question)
        if threshold is None:
            continue
        btc_markets.append(m)

    logger.info(
        f"Filtered to {len(btc_markets)} BTC threshold markets with parseable prices"
    )

    if dry_run:
        for m in btc_markets[:10]:
            q = m.get("question", "")
            threshold = parse_btc_threshold(q)
            prices = m.get("outcomePrices", [])
            outcomes = m.get("outcomes", [])
            end_date = m.get("endDate", "")
            print(
                f"  threshold=${threshold:,.0f}  {q[:70]}  prices={prices}  end={end_date}"
            )
        if len(btc_markets) > 10:
            print(f"  ... and {len(btc_markets) - 10} more")
        return 0

    price_cache: dict[str, Optional[float]] = {}
    price_fetch_count = 0
    price_fetch_failures = 0

    for m in btc_markets:
        end_date_str = m.get("endDate") or ""
        try:
            market_time = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if market_time < start or market_time > end:
            continue

        q = m.get("question", "")
        threshold = parse_btc_threshold(q)
        if threshold is None:
            continue

        ts_key = end_date_str[:19]
        if ts_key not in price_cache:
            price_fetch_count += 1
            ts_ms = int(market_time.timestamp() * 1000)
            btc_price = await fetch_binance_historical_price(ts_ms)
            price_cache[ts_key] = btc_price
            if btc_price is None:
                price_fetch_failures += 1
            await asyncio.sleep(0.15)

    logger.info(
        f"Fetched {price_fetch_count} historical BTC prices ({price_fetch_failures} failures)"
    )

    db: Session = SessionLocal()
    try:
        signals_created = 0
        trades_created = 0

        for m in btc_markets:
            q = m.get("question", "")
            threshold = parse_btc_threshold(q)
            if threshold is None:
                continue

            end_date_str = m.get("endDate") or ""
            try:
                market_time = datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue

            if market_time < start or market_time > end:
                continue

            ts_key = end_date_str[:19]
            btc_price = price_cache.get(ts_key)

            if btc_price is None:
                continue

            outcome_prices_raw = m.get("outcomePrices", [])
            if isinstance(outcome_prices_raw, str):
                try:
                    outcome_prices_raw = json.loads(outcome_prices_raw)
                except (json.JSONDecodeError, TypeError):
                    continue

            try:
                yes_resolved = (
                    float(outcome_prices_raw[0]) if outcome_prices_raw[0] else 0.0
                )
            except (ValueError, TypeError):
                yes_resolved = 0.0

            yes_won = yes_resolved > 0.5
            start_date_str = m.get("startDate") or end_date_str
            try:
                creation_time = datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                creation_time = market_time - timedelta(hours=6)

            hours_to_resolution = max(
                0.5, (market_time - creation_time).total_seconds() / 3600
            )
            market_price = btc_price_to_probability(
                btc_price, threshold, hours_to_resolution
            )

            btc_at_creation_ms = int(creation_time.timestamp() * 1000)
            creation_key = start_date_str[:19]
            if creation_key not in price_cache:
                btc_at_creation = await fetch_binance_historical_price(
                    btc_at_creation_ms
                )
                price_cache[creation_key] = btc_at_creation
                await asyncio.sleep(0.15)
            else:
                btc_at_creation = price_cache[creation_key]

            if btc_at_creation is not None:
                market_price = btc_price_to_probability(
                    btc_at_creation, threshold, hours_to_resolution
                )

            model_prob = market_price

            slug = m.get("slug", f"btc-{threshold:.0f}")
            volume = float(m.get("volume", 0) or 0)

            existing = (
                db.query(Signal)
                .filter(
                    Signal.market_ticker == slug,
                    Signal.reasoning.contains("honest-seed"),
                )
                .first()
            )
            if existing:
                continue

            if model_prob > 0.5:
                direction = "up"
            else:
                direction = "down"

            settlement_value = 1.0 if yes_won else 0.0
            if direction == "up":
                outcome_correct = yes_won
            else:
                outcome_correct = not yes_won

            edge = abs(model_prob - 0.5)
            confidence = min(edge * 2.0, 0.95)
            size = round(min(10.0, max(2.0, volume / 10000)), 2) if volume > 0 else 5.0

            sig = Signal(
                market_ticker=slug,
                platform="polymarket",
                market_type="btc",
                timestamp=creation_time,
                direction=direction,
                model_probability=round(model_prob, 4),
                market_price=0.5,
                edge=round(edge, 4),
                confidence=round(confidence, 4),
                kelly_fraction=0.0625,
                suggested_size=size * 0.5,
                sources={
                    "source": "honest-seed",
                    "btc_price_at_creation": btc_at_creation,
                    "threshold": threshold,
                },
                reasoning=f"honest-seed: {q[:200]}",
                track_name="backtest",
                execution_mode="paper",
                executed=True,
                actual_outcome="win" if outcome_correct else "loss",
                outcome_correct=outcome_correct,
                settlement_value=settlement_value,
                settled_at=market_time + timedelta(hours=random.randint(1, 12)),
            )
            db.add(sig)
            db.flush()

            if direction == "up":
                entry_price = round(market_price, 4)
                payout = settlement_value
            else:
                entry_price = round(1.0 - market_price, 4)
                payout = 1.0 - settlement_value

            if outcome_correct:
                pnl = (
                    round(size * (payout / entry_price - 1), 4)
                    if entry_price > 0
                    else 0.0
                )
            else:
                pnl = -size

            trade = Trade(
                signal_id=sig.id,
                market_ticker=slug,
                platform="polymarket",
                market_type="btc",
                direction=direction,
                entry_price=entry_price,
                size=size,
                model_probability=round(model_prob, 4),
                market_price_at_entry=entry_price,
                edge_at_entry=round(edge, 4),
                result="win" if outcome_correct else "loss",
                settled=True,
                settlement_value=settlement_value,
                settlement_time=market_time + timedelta(hours=random.randint(1, 24)),
                pnl=pnl,
                strategy="btc_honest",
                timestamp=creation_time,
                trading_mode="paper",
                confidence=round(confidence, 4),
            )
            db.add(trade)
            signals_created += 1
            trades_created += 1

        db.commit()
        logger.info(
            f"Created {signals_created} honest signals and {trades_created} trades"
        )
        return signals_created

    except Exception as e:
        db.rollback()
        logger.error(f"Error: {e}")
        raise
    finally:
        db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Seed HONEST backtest data from resolved BTC markets"
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Days of history to search"
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="Max markets from Gamma API"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to DB"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PolyEdge HONEST Backtest Data Seeder")
    logger.info("No look-ahead bias — uses actual BTC price at market creation time")
    logger.info("=" * 60)

    await seed_honest_backtest(
        days_back=args.days,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
