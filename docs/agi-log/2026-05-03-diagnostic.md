# Diagnostic — 2026-05-03 13:55 UTC

## TL;DR
All trades blocked by drawdown breaker (7d paper loss $343.25 > 30% limit). btc_oracle strategy has 0% win rate (33/33 losses) with model_probability=1.0 always predicting same direction. Three test failures fixed: stale WalletWatcher test, SessionLocal test isolation across conftest files.

## Findings
| # | Finding | Severity | Fix |
|---|---------|----------|-----|
| 1 | Drawdown breaker blocking ALL trades (100,985 rejections/7d) | 🔴 Critical | Correct behavior — breaker protects against btc_oracle losses. Self-clears when losses age past 7d window. |
| 2 | btc_oracle 0% win rate, model_probability always 1.0 | 🔴 Critical | Operational — oracle model predicting same direction with certainty. Strategy disabled in DB (enabled=0) but still generating signals. |
| 3 | 7 of 9 target strategies disabled (enabled=0) | 🟡 High | Operational — only copy_trader, whale_frontrun, weather_emos, kalshi_arb, whale_pnl_tracker enabled. None producing executed trades due to drawdown breaker. |
| 4 | MIN_EDGE_THRESHOLD=0.30 in .env — very high | 🟡 High | Config — filtering most signals. general_scanner avg_edge=0.034 blocked. Weather passes (0.32-0.45) but Kalshi disabled. |
| 5 | KALSHI_ENABLED=false blocks weather signals | 🟡 Medium | Config — weather_emos generates Kalshi signals but exchange disabled. |
| 6 | test_copy_trader WalletWatcher test stale | 🟡 Medium | Fixed — test expected empty first poll but impl intentionally changed to return initial trades. |
| 7 | test_autonomy_loop_integration SessionLocal isolation | 🔴 Critical | Fixed — two conftest files patching same _db_mod with different engines; 25+ modules capture stale SessionLocal at import time. |
| 8 | docs/agi-log/ missing | 🟢 Low | Fixed — created directory with .gitkeep. |
| 9 | backend/polyedge.db and data/polyedge.db empty (0 bytes) | 🟢 Info | Not a bug — actual DB is tradingbot.db (per .env DATABASE_URL). |

## Last Trade: [live] [manual] [2026-05-02 06:28:40] PnL=-24.50
## Last Bot Trade: [live] [btc_oracle] [2026-05-02 06:21:44] PnL=-25.25 (loss)

## Root Causes (low trades):
1. **btc_oracle catastrophic losses** ($410 live, $323 paper) → triggered weekly drawdown breaker
2. **Drawdown breaker correctly tripped** — 7d loss exceeds 30% limit → blocks all strategies
3. **Most strategies disabled** — only 5 of 9+ enabled, none bypassing drawdown
4. **btc_oracle model broken** — model_probability=1.0 with 100% loss rate, always predicts same direction
5. **Drawdown self-clears** after losses age past 7d window (btc_oracle losses from 2026-05-01)

## Fixes Applied:
- `tests/test_copy_trader.py`: Updated test_first_poll to expect trades on first poll (impl intentionally changed)
- `backend/tests/conftest.py`: Patched SessionLocal in 25+ production modules + used savepoint-based transaction management to fix cross-conftest isolation
- `backend/tests/test_autonomy_loop_integration.py`: Changed from static `SessionLocal` import to `_db_mod.SessionLocal` for dynamic resolution
- Created `docs/agi-log/` directory

## Tests: pytest 1779 passed | npm test 132 passed — 0 failures
