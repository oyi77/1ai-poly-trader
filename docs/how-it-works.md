# How It Works

## BTC 5-Minute Strategy

1. Fetch 60 one-minute candles from Coinbase/Kraken/Binance (fallback chain)
2. Compute 5 indicators: RSI(14), Momentum(1m/5m/15m), VWAP deviation, SMA crossover, Market skew
3. Convergence filter: require 2+ of 4 indicators to agree
4. Weighted composite -> model UP probability (0.35-0.65 range)
5. Compare to Polymarket prices, trade the side with higher edge

## Weather Temperature Strategy

1. Fetch open weather markets from Kalshi (KXHIGH series, RSA-PSS auth) and Polymarket (Gamma API)
2. Fetch 31-member GFS ensemble forecasts from Open-Meteo
3. Count fraction of members above/below the market's temperature threshold
4. That fraction = model probability (e.g., 28/31 members above 70F = 90% probability)
5. Compare to market price on either platform, trade when edge > 8%
6. Confidence = ensemble agreement (how one-sided the 31 members are)

## Edge Calculation

```
edge = model_probability - market_probability
```
BTC signals require |edge| > 2%. Weather signals require |edge| > 8%.

## Position Sizing (Fractional Kelly)

```
kelly = (win_prob * odds - lose_prob) / odds
position_size = kelly * 0.15 * bankroll
```
Capped at 5% of bankroll and $75 (BTC) or $100 (Weather) per trade.
