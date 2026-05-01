import asyncio
import logging
import sys
from unittest.mock import MagicMock, AsyncMock
from backend.strategies.copy_trader import CopyTrader

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_copy_trader():
    # Mock bankroll and params
    copy_trader = CopyTrader(bankroll=1000.0, max_wallets=2, min_score=60.0)
    
    # Mock the scorer and watcher
    copy_trader._scorer = AsyncMock()
    copy_trader._watcher = AsyncMock()
    
    # Setup mock leaderboard
    trader = MagicMock()
    trader.wallet = "0x123"
    trader.score = 95.0
    trader.pseudonym = "Whale1"
    copy_trader._tracked = [trader]
    copy_trader._last_refresh = asyncio.get_running_loop().time()
    
    # Setup mock new trades
    mock_trade = MagicMock()
    mock_trade.condition_id = "cond_abc"
    copy_trader._watcher.poll.side_effect = [
        ([mock_trade], []), # Whale 1 new buy
    ]
    
    # Mock executor
    copy_trader._executor = AsyncMock()
    signal = MagicMock()
    signal.source_wallet = "0x123"
    signal.source_trade = mock_trade
    signal.trader_score = 95.0
    signal.our_size = 50.0
    signal.our_side = "BUY"
    signal.market_price = 0.65
    signal.reasoning = "Mirroring high-score trader"
    
    copy_trader._executor.mirror_buy_async.return_value = signal
    
    print("Polling copy trader...")
    signals = await copy_trader.poll_once()
    
    if signals:
        print(f"Generated {len(signals)} copy signals")
        for s in signals:
            print(f"Signal: {s.our_side} {s.our_size} on {s.source_trade.condition_id} (score={s.trader_score})")
    else:
        print("No signals generated.")

if __name__ == "__main__":
    asyncio.run(test_copy_trader())
