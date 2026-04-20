import { motion } from 'framer-motion'

interface Trade {
  id: string
  market_ticker: string
  direction: 'up' | 'down'
  entry_price: number
  exit_price: number
  pnl: number
  timestamp: string
}

interface WinningTradesPreviewProps {
  trades: Trade[]
  onViewAll?: () => void
}

export function WinningTradesPreview({ trades, onViewAll }: WinningTradesPreviewProps) {
  const topTrades = trades
    .filter(t => t.pnl > 0)
    .sort((a, b) => b.pnl - a.pnl)
    .slice(0, 5)

  if (topTrades.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <span className="text-xs text-neutral-600">No winning trades yet</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between shrink-0">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Top Winning Trades</span>
        {onViewAll && (
          <button
            onClick={onViewAll}
            className="text-[9px] text-green-500 hover:text-green-400 uppercase tracking-wider transition-colors"
          >
            View All →
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-neutral-950">
            <tr className="border-b border-neutral-800">
              <th className="px-3 py-1.5 text-left text-neutral-600 uppercase tracking-wider font-normal">Market</th>
              <th className="px-3 py-1.5 text-left text-neutral-600 uppercase tracking-wider font-normal">Dir</th>
              <th className="px-3 py-1.5 text-right text-neutral-600 uppercase tracking-wider font-normal">Entry</th>
              <th className="px-3 py-1.5 text-right text-neutral-600 uppercase tracking-wider font-normal">Exit</th>
              <th className="px-3 py-1.5 text-right text-neutral-600 uppercase tracking-wider font-normal">Profit</th>
            </tr>
          </thead>
          <tbody>
            {topTrades.map((trade, idx) => (
              <motion.tr
                key={trade.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="border-b border-neutral-800/40 hover:bg-neutral-900/30 transition-colors"
              >
                <td className="px-3 py-2 text-neutral-400 truncate max-w-[120px]" title={trade.market_ticker}>
                  {trade.market_ticker.length > 20 ? `${trade.market_ticker.slice(0, 18)}...` : trade.market_ticker}
                </td>
                <td className="px-3 py-2">
                  <span className={`font-bold ${trade.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                    {trade.direction === 'up' ? '↑' : '↓'}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-neutral-500 tabular-nums">
                  {(trade.entry_price * 100).toFixed(1)}¢
                </td>
                <td className="px-3 py-2 text-right text-neutral-500 tabular-nums">
                  {(trade.exit_price * 100).toFixed(1)}¢
                </td>
                <td className="px-3 py-2 text-right font-semibold text-green-500 tabular-nums">
                  +${trade.pnl.toFixed(2)}
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
