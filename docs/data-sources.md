# Data Sources

| Source | Data | Used For | Auth |
|--------|------|----------|------|
| Coinbase | BTC 1-min candles | BTC microstructure | None |
| Kraken | BTC 1-min candles | BTC fallback | None |
| Binance | BTC 1-min candles | BTC fallback | None |
| Open-Meteo | GFS Ensemble (31 members) | Weather probability | None |
| NWS API | Observed temperatures | Weather settlement | None |
| Polymarket | Market prices + resolution | Both strategies | None |
| Kalshi | Weather temperature markets (KXHIGH) | Weather strategy | RSA key |

## Supported Cities (Weather)

| City | Station | Tracked |
|------|---------|---------|
| New York | KNYC | Default |
| Chicago | KORD | Default |
| Miami | KMIA | Default |
| Los Angeles | KLAX | Default |
| Denver | KDEN | Default |

Add more cities by editing `WEATHER_CITIES` in config and adding entries to `CITY_CONFIG` in `backend/data/weather.py`.
