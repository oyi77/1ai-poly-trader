import { useQuery } from '@tanstack/react-query'
import { fetchBtcWindows, fetchPolymarketMarkets, type PolymarketMarket } from '../../api'
import type { BtcWindow } from '../../types'
import { formatCountdown } from '../../utils'

export function MarketsTab() {
  const { data: btcWindows = [] } = useQuery({
    queryKey: ['btc-windows-tab'],
    queryFn: fetchBtcWindows,
    refetchInterval: 10_000,
  })

  // Polymarket markets - fetch all (no pagination)
  const { data: polymarketMarkets = [], isLoading: pmLoading } = useQuery({
    queryKey: ['polymarket-markets-all'],
    queryFn: () => fetchPolymarketMarkets(0, 5000), // Fetch up to 5000 markets
    refetchInterval: 60_000,
  })

  return (
    <div className="grid grid-cols-2 gap-0 h-full min-h-0 divide-x divide-neutral-800">
      {/* BTC Windows */}
      <div className="flex flex-col min-h-0">
        <div className="px-3 py-2 border-b border-neutral-800 shrink-0">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider">BTC Windows</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-neutral-950">
              <tr className="border-b border-neutral-800">
                <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Time</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Up</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Down</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Vol</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Remaining</th>
              </tr>
            </thead>
            <tbody>
              {btcWindows.map((w: BtcWindow) => (
                <tr key={w.slug} className={`border-b border-neutral-800/40 ${w.is_active ? 'bg-green-500/5' : 'hover:bg-neutral-900/30'}`}>
                  <td className="px-3 py-1 text-neutral-400 whitespace-nowrap">
                    {w.is_active && <span className="text-[9px] text-amber-400 uppercase mr-1">Live</span>}
                    {w.is_upcoming && <span className="text-[9px] text-blue-400 uppercase mr-1">Next</span>}
                    {w.slug?.split('-').slice(-1)[0] ?? '—'}
                  </td>
                  <td className="px-3 py-1 text-right text-green-400 tabular-nums">{(w.up_price * 100).toFixed(1)}c</td>
                  <td className="px-3 py-1 text-right text-red-400 tabular-nums">{(w.down_price * 100).toFixed(1)}c</td>
                  <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{w.volume != null ? `$${(w.volume / 1000).toFixed(0)}k` : '—'}</td>
                  <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{formatCountdown(w.time_until_end)}</td>
                </tr>
              ))}
              {btcWindows.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-neutral-700">No BTC windows</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Polymarket Markets */}
      <div className="flex flex-col min-h-0">
        <div className="px-3 py-2 border-b border-neutral-800 shrink-0 flex items-center justify-between">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Polymarket</span>
          <span className="text-[9px] text-neutral-600">{polymarketMarkets.length} markets</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          {pmLoading ? (
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
                    <td className="px-3 py-1 text-neutral-300 truncate max-w-[80px]" title={m.ticker}>{m.ticker.slice(0, 8)}...</td>
                    <td className="px-3 py-1 text-neutral-500 truncate max-w-[150px]" title={m.question}>{m.question}</td>
                    <td className="px-3 py-1 text-right text-green-400 tabular-nums">{(m.yes_price * 100).toFixed(1)}¢</td>
                    <td className="px-3 py-1 text-right text-red-400 tabular-nums">{(m.no_price * 100).toFixed(1)}¢</td>
                    <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{m.volume > 0 ? `$${(m.volume / 1000).toFixed(0)}k` : '—'}</td>
                  </tr>
                ))}
                {polymarketMarkets.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-neutral-700">No markets</td></tr>}
              </tbody>
            </table>
          )}
        </div>

      </div>
    </div>
  )
}
