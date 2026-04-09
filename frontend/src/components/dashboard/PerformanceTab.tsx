import { useQuery } from '@tanstack/react-query'
import { useStats } from '../../hooks/useStats'
import { fetchHealth, fetchTrades } from '../../api'
import type { StrategyHealth } from '../../api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

export function PerformanceTab() {
  const { pnl, bankroll, winRate, trades } = useStats()
  const { data: health } = useQuery({
    queryKey: ['health-perf'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  })
  const { data: allTrades = [] } = useQuery({
    queryKey: ['trades-perf'],
    queryFn: () => fetchTrades(),
    refetchInterval: 30_000,
  })

  const strategies: StrategyHealth[] = health?.strategies ?? []

  const paperTrades = allTrades.filter((t: any) => t.trading_mode === 'paper')
  const liveTrades = allTrades.filter((t: any) => t.trading_mode === 'live')
  const paperWins = paperTrades.filter((t: any) => t.result === 'win').length
  const paperSettled = paperTrades.filter((t: any) => t.result === 'win' || t.result === 'loss').length
  const liveWins = liveTrades.filter((t: any) => t.result === 'win').length
  const liveSettled = liveTrades.filter((t: any) => t.result === 'win' || t.result === 'loss').length

  const chartData = [
    { name: 'Paper', winRate: paperSettled > 0 ? (paperWins / paperSettled) * 100 : 0 },
    { name: 'Live', winRate: liveSettled > 0 ? (liveWins / liveSettled) * 100 : 0 },
  ]

  const todayStart = new Date(); todayStart.setHours(0, 0, 0, 0)
  const dailyPnl = allTrades
    .filter((t: any) => t.timestamp && new Date(t.timestamp) >= todayStart)
    .reduce((s: number, t: any) => s + (t.pnl ?? 0), 0)

  const avgTradeSize = allTrades.length > 0 ? allTrades.reduce((s: number, t: any) => s + (t.size ?? 0), 0) / allTrades.length : 0

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {/* Key Metrics Grid */}
      <div>
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Key Metrics</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'Bankroll', value: `$${bankroll.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, color: 'text-neutral-200' },
            { label: 'Total PNL', value: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`, color: pnl >= 0 ? 'text-green-500' : 'text-red-500' },
            { label: 'Win Rate', value: `${winRate.toFixed(1)}%`, color: winRate >= 50 ? 'text-green-500' : 'text-amber-400' },
            { label: 'Total Trades', value: String(trades), color: 'text-neutral-300' },
            { label: 'Avg Trade Size', value: `$${avgTradeSize.toFixed(0)}`, color: 'text-neutral-300' },
            { label: 'Daily PNL', value: `${dailyPnl >= 0 ? '+' : ''}$${dailyPnl.toFixed(2)}`, color: dailyPnl >= 0 ? 'text-green-500' : 'text-red-500' },
          ].map(m => (
            <div key={m.label} className="border border-neutral-800 bg-neutral-900/20 p-3">
              <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-1">{m.label}</div>
              <div className={`text-sm font-semibold tabular-nums font-mono ${m.color}`}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Win Rate Chart */}
      <div>
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Win Rate by Mode</div>
        <div className="border border-neutral-800 bg-neutral-900/20 p-3" style={{ height: '140px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#737373' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#737373' }} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
              <Tooltip
                contentStyle={{ background: '#0a0a0a', border: '1px solid #262626', borderRadius: 0, fontSize: 10 }}
                formatter={(v: number) => [`${v.toFixed(1)}%`, 'Win Rate']}
              />
              <Bar dataKey="winRate" radius={0}>
                {chartData.map((entry, index) => (
                  <Cell key={index} fill={entry.winRate >= 50 ? '#22c55e' : '#f59e0b'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Strategy Health */}
      <div>
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Strategy Health</div>
        <div className="space-y-1">
          {strategies.map((s: StrategyHealth) => (
            <div key={s.name} className="border border-neutral-800 px-3 py-2 flex items-center gap-4">
              <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.healthy ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-[10px] text-neutral-300 font-mono flex-1">{s.name}</span>
              <span className="text-[9px] text-neutral-600">
                {s.last_heartbeat ? new Date(s.last_heartbeat).toLocaleTimeString('en-US', { hour12: false }) : 'never'}
              </span>
              {s.lag_seconds != null && (
                <span className={`text-[9px] tabular-nums ${s.lag_seconds > 120 ? 'text-red-400' : 'text-neutral-500'}`}>
                  {s.lag_seconds.toFixed(0)}s lag
                </span>
              )}
              <span className={`text-[9px] uppercase tracking-wider ${s.healthy ? 'text-green-500' : 'text-red-500'}`}>
                {s.healthy ? 'healthy' : 'stale'}
              </span>
            </div>
          ))}
          {strategies.length === 0 && (
            <div className="text-[10px] text-neutral-600 py-2">
              Bot not running — start from Admin panel
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
