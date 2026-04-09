import { useQuery } from '@tanstack/react-query'
import { fetchPolymarketMarkets, type PolymarketMarket } from '../../api'

export function MarketsTab() {
  const { data: polymarketMarkets = [], isLoading } = useQuery({
    queryKey: ['polymarket-markets-all'],
    queryFn: () => fetchPolymarketMarkets(0, 5000),
    refetchInterval: 60_000,
  })

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Polymarket Markets</span>
        <span className="text-[9px] text-neutral-600 tabular-nums">{polymarketMarkets.length} markets</span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {isLoading ? (
          <div className="px-3 py-6 text-center text-neutral-600 text-[10px]">Loading...</div>
        ) : (
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-neutral-950">
              <tr className="border-b border-neutral-800">
                <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Ticker</th>
                <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Question</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Yes</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">No</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Volume</th>
              </tr>
            </thead>
            <tbody>
              {polymarketMarkets.map((m: PolymarketMarket) => (
                <tr key={m.ticker} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                  <td className="px-3 py-1 text-neutral-300 truncate max-w-[100px]" title={m.ticker}>{m.ticker.length > 12 ? `${m.ticker.slice(0, 10)}...` : m.ticker}</td>
                  <td className="px-3 py-1 text-neutral-500 truncate max-w-[300px]" title={m.question}>{m.question}</td>
                  <td className="px-3 py-1 text-right text-green-400 tabular-nums">{(m.yes_price * 100).toFixed(1)}c</td>
                  <td className="px-3 py-1 text-right text-red-400 tabular-nums">{(m.no_price * 100).toFixed(1)}c</td>
                  <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{m.volume > 0 ? `$${(m.volume / 1000).toFixed(0)}k` : '--'}</td>
                </tr>
              ))}
              {polymarketMarkets.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-neutral-700">No markets</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
