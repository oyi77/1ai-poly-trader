import asyncio
import logging
import sys
from unittest.mock import MagicMock, AsyncMock
from backend.strategies.copy_trader import CopyTrader
from backend.strategies.wallet_sync import WalletTrade

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def test_copy_trader():
    # Mock bankroll and params
    copy_trader = CopyTrader(bankroll=1000.0, max_wallets=2, min_score=60.0)
    
    # Mock the scorer and watcher to avoid external API calls in this test
    copy_trader._scorer = AsyncMock()
    copy_trader._watcher = AsyncMock()
    
    # Setup mock leaderboard
    from backend.strategies.order_executor import ScoredTrader
    copy_trader._tracked = [
        ScoredTrader(wallet="0x123", score=95.0, pseudonym="Whale1"),
        ScoredTrader(wallet="0x456", score=80.0, pseudonym="Whale2")
    ]
    copy_trader._last_refresh = asyncio.get_running_loop().time()
    
    # Setup mock new trades
    mock_trade = WalletTrade(
        wallet_address="0x123",
        condition_id="cond_abc",
        type="BUY",
        amount=500.0,
        price=0.65,
        timestamp=1234567890
    )
    copy_trader._watcher.poll.side_effect = [
        ([mock_trade], []), # Whale 1 new buy
        ([], [])            # Whale 2 no trades
    ]
    
    # Mock executor
    copy_trader._executor = AsyncMock()
    from backend.strategies.order_executor import CopySignal
    copy_trader._executor.mirror_buy_async.return_value = CopySignal(
        source_wallet="0x123",
        source_trade=mock_trade,
        trader_score=95.0,
        our_size=50.0,
        our_side="BUY",
        market_price=0.65,
        reasoning="Mirroring high-score trader"
    )
    
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
