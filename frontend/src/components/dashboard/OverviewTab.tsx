import { useState, useEffect, Suspense, lazy } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useStats } from '../../hooks/useStats'
import { SignalsTable } from '../SignalsTable'
import { TradesTable } from '../TradesTable'
import { EquityChart } from '../EquityChart'
import { Terminal } from '../Terminal'
import { MicrostructurePanel } from '../MicrostructurePanel'
import { CalibrationPanel } from '../CalibrationPanel'
import { WeatherPanel } from '../WeatherPanel'
import { EdgeDistribution } from '../EdgeDistribution'
import { fetchSignalHistory } from '../../api'
import { formatCountdown } from '../../utils'
import type { SignalHistoryRow } from '../../api'
import type { BtcWindow } from '../../types'

const GlobeView = lazy(() => import('../GlobeView').then(m => ({ default: m.GlobeView })))

// ── WindowPill Helper ───────────────────────────────────────────────────────────

export function WindowPill({ window: w }: { window: BtcWindow }) {
  const [countdown, setCountdown] = useState(w.time_until_end)
  useEffect(() => {
    const interval = setInterval(() => {
      setCountdown(prev => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(interval)
  }, [w.time_until_end])
  return (
    <div className={`flex items-center gap-2 px-2 py-1 border shrink-0 ${w.is_active ? 'border-amber-500/30 bg-amber-500/5' : 'border-neutral-800 bg-neutral-900/50'}`}>
      {w.is_active && <span className="text-[9px] font-bold text-amber-400 uppercase">Live</span>}
      {w.is_upcoming && <span className="text-[9px] font-medium text-blue-400 uppercase">Next</span>}
      <span className="text-[10px] tabular-nums text-green-400">{(w.up_price * 100).toFixed(0)}c</span>
      <span className="text-neutral-600 text-[10px]">/</span>
      <span className="text-[10px] tabular-nums text-red-400">{(w.down_price * 100).toFixed(0)}c</span>
      <span className="text-[10px] tabular-nums text-neutral-500">{formatCountdown(countdown)}</span>
    </div>
  )
}

// ── SignalsPanel Helper ───────────────────────────────────────────────────────

interface SignalsPanelProps {
  activeSignals: ReturnType<typeof Array.prototype.slice>
  weatherSignals: ReturnType<typeof Array.prototype.slice>
  onSimulateTrade: (ticker: string) => void
  isSimulating: boolean
}

function SignalsPanel({ activeSignals, weatherSignals, onSimulateTrade, isSimulating }: SignalsPanelProps) {
  const [tab, setTab] = useState<'live' | 'history'>('live')

  const { data: historyData, isLoading, isError } = useQuery({
    queryKey: ['signals-history'],
    queryFn: () => fetchSignalHistory({ limit: 100 }),
    enabled: tab === 'history',
    refetchInterval: tab === 'history' ? 30_000 : false,
  })

  const history: SignalHistoryRow[] = (isLoading || isError) ? [] : (historyData?.items ?? [])

  return (
    <div className="flex flex-col min-h-0" style={{ height: '50%' }}>
      <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Signals</span>
          <div className="flex gap-1">
            {(['live', 'history'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 transition-colors ${
                  tab === t
                    ? 'text-neutral-200 border-b border-neutral-400'
                    : 'text-neutral-600 hover:text-neutral-400'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {tab === 'live' ? (
            <>
              <span className="text-[10px] text-amber-400 tabular-nums">{(activeSignals as unknown[]).length} BTC</span>
              {(weatherSignals as unknown[]).length > 0 && (
                <span className="text-[10px] text-cyan-400 tabular-nums">{(weatherSignals as unknown[]).length} WX</span>
              )}
            </>
          ) : (
            <span className="text-[10px] text-neutral-600 tabular-nums">{historyData?.total ?? 0} total</span>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === 'live' ? (
          <SignalsTable
            signals={activeSignals as Parameters<typeof SignalsTable>[0]['signals']}
            weatherSignals={weatherSignals as Parameters<typeof SignalsTable>[0]['weatherSignals']}
            onSimulateTrade={onSimulateTrade}
            isSimulating={isSimulating}
          />
        ) : (
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-neutral-950">
              <tr className="border-b border-neutral-800">
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Time</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Market</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Dir</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Edge</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Conf</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Exec</td>
                <td className="px-2 py-1 text-neutral-600 uppercase tracking-wider">Result</td>
              </tr>
            </thead>
            <tbody>
              {history.map(row => (
                <tr key={row.id} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                  <td className="px-2 py-1 text-neutral-600">
                    {row.timestamp ? new Date(row.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }) : '—'}
                  </td>
                  <td className="px-2 py-1 text-neutral-400 truncate max-w-[80px]" title={row.market_ticker}>
                    {row.market_ticker.length > 16 ? `${row.market_ticker.slice(0, 14)}…` : row.market_ticker}
                  </td>
                  <td className={`px-2 py-1 font-bold ${row.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                    {row.direction?.toUpperCase()}
                  </td>
                  <td className="px-2 py-1 text-neutral-300 tabular-nums">
                    {row.edge != null ? `${(row.edge * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-2 py-1 text-neutral-500 tabular-nums">
                    {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : '—'}
                  </td>
                  <td className="px-2 py-1">
                    <span className={row.executed ? 'text-green-500' : 'text-neutral-700'}>
                      {row.executed ? '✓' : '—'}
                    </span>
                  </td>
                  <td className="px-2 py-1">
                    {row.outcome_correct == null ? (
                      <span className="text-neutral-700">pending</span>
                    ) : row.outcome_correct ? (
                      <span className="text-green-500">win</span>
                    ) : (
                      <span className="text-red-500">loss</span>
                    )}
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-2 py-4 text-center text-neutral-700">No signal history</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Overview Tab ─────────────────────────────────────────────────────────────

export interface OverviewTabProps {
  data: Awaited<ReturnType<any>>
  equityCurve: any
  activeSignals: any
  recentTrades: any
  weatherSignals: any
  weatherForecasts: any
  calibration: any
  windows: BtcWindow[]
  micro: any
  onSimulateTrade: (ticker: string) => void
  isSimulating: boolean
  onStart: () => void
  onStop: () => void
  onScan: () => void
}

export function OverviewTab({
  data: _data,
  equityCurve, activeSignals, recentTrades, weatherSignals,
  weatherForecasts, calibration, windows, micro,
  onSimulateTrade, isSimulating, onStart, onStop, onScan,
}: OverviewTabProps) {
  const stats = useStats()
  const actionableCount = activeSignals.filter((s: any) => s.actionable).length + weatherSignals.filter((s: any) => s.actionable).length

  return (
    <div className="flex-1 min-h-0 grid grid-cols-[300px_1fr_340px] gap-0">
      {/* LEFT */}
      <div className="flex flex-col border-r border-neutral-800 min-h-0 overflow-hidden">
        {micro && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="shrink-0 border-b border-neutral-800 px-2 py-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Microstructure</span>
              <span className="text-[9px] text-neutral-600 tabular-nums">{micro.source}</span>
            </div>
            <MicrostructurePanel micro={micro} />
          </motion.div>
        )}
        <div className="border-b border-neutral-800" style={{ height: '35%', minHeight: '180px' }}>
          <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
            <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Equity</span>
            <div className="flex items-center gap-2">
              <span className="text-[10px] tabular-nums text-neutral-200">${stats.totalEquity.toFixed(0)}</span>
              <span className={`text-[10px] tabular-nums ${stats.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {stats.pnl >= 0 ? '+' : ''}${stats.pnl.toFixed(0)}
              </span>
            </div>
          </div>
          <div className="h-[calc(100%-24px)] p-1">
            <EquityChart data={equityCurve} initialBankroll={stats.bankroll - stats.pnl} />
          </div>
        </div>
        {(stats.paperStats || stats.liveStats) && (
          <div className="shrink-0 border-b border-neutral-800 px-2 py-2 flex gap-2">
            {(['paper', 'live'] as const).map(modeKey => {
              const modeData = modeKey === 'paper' ? stats.paperStats : stats.liveStats
              if (!modeData) return null
              const isActive = stats.mode === modeKey
              return (
                <div key={modeKey} className={`flex-1 border px-2 py-1.5 ${isActive ? modeKey === 'live' ? 'border-red-500/40 bg-red-500/5' : 'border-amber-500/40 bg-amber-500/5' : 'border-neutral-800 bg-neutral-900/30'}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-[9px] uppercase tracking-wider font-bold ${isActive ? modeKey === 'live' ? 'text-red-400' : 'text-amber-400' : 'text-neutral-600'}`}>{modeKey === 'live' ? 'Live' : 'Paper'}</span>
                    {isActive && <span className={`text-[8px] uppercase px-1 py-0.5 border ${modeKey === 'live' ? 'text-red-400 border-red-500/30 bg-red-500/10' : 'text-amber-400 border-amber-500/30 bg-amber-500/10'}`}>Active</span>}
                  </div>
                  <div className={`text-xs font-semibold tabular-nums ${modeData.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{modeData.pnl >= 0 ? '+' : ''}${modeData.pnl.toFixed(0)}</div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[9px] text-neutral-600 tabular-nums">{modeData.trades}t</span>
                    <span className="text-[9px] text-neutral-600 tabular-nums">{(modeData.win_rate * 100).toFixed(0)}%w</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {calibration && calibration.total_with_outcome > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="shrink-0 border-b border-neutral-800 px-2 py-2">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Calibration</span>
              <span className="text-[9px] text-neutral-600 tabular-nums">{calibration.total_with_outcome} settled</span>
            </div>
            <CalibrationPanel calibration={calibration} />
          </motion.div>
        )}
        <div className="flex-1 min-h-0">
          <Terminal
            isRunning={stats.isRunning}
            lastRun={stats.lastRun}
            stats={{ total_trades: stats.trades, total_pnl: stats.pnl }}
            onStart={onStart}
            onStop={onStop}
            onScan={onScan}
          />
        </div>
      </div>

      {/* CENTER */}
      <div className="flex flex-col min-h-0 border-r border-neutral-800">
        <div className="relative" style={{ height: '58%' }}>
          <div className="absolute inset-0">
            <Suspense fallback={<div className="w-full h-full flex items-center justify-center bg-black"><span className="text-[10px] text-neutral-600 uppercase tracking-wider">Loading Globe...</span></div>}>
              <GlobeView forecasts={weatherForecasts} signals={weatherSignals} />
            </Suspense>
          </div>
          <div className="absolute top-2 left-2 z-10">
            <div className="px-2 py-1 bg-black/80 border border-neutral-800 text-[10px]">
              <span className="text-neutral-500 uppercase tracking-wider mr-2">Markets</span>
              <span className="text-amber-500 tabular-nums">{actionableCount} actionable</span>
            </div>
          </div>
        </div>
        <div className="flex-1 min-h-0 grid grid-cols-3 border-t border-neutral-800">
          <div className="border-r border-neutral-800 flex flex-col min-h-0">
            <div className="px-2 py-1 border-b border-neutral-800 shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Edge Distribution</span>
            </div>
            <div className="flex-1 min-h-0 p-1">
              <EdgeDistribution btcSignals={activeSignals} weatherSignals={weatherSignals} />
            </div>
          </div>
          <div className="border-r border-neutral-800 flex flex-col min-h-0">
            <div className="px-2 py-1 border-b border-neutral-800 shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">BTC Windows</span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-1 space-y-1">
              {windows.length > 0 ? windows.slice(0, 10).map(w => <WindowPill key={w.slug} window={w} />) : <div className="text-[10px] text-neutral-600 p-2">No active windows</div>}
            </div>
          </div>
          <div className="flex flex-col min-h-0">
            <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Weather</span>
              <span className="px-1 py-0.5 text-[8px] font-bold uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">WX</span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto">
              <WeatherPanel forecasts={weatherForecasts} signals={weatherSignals} />
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT */}
      <div className="flex flex-col min-h-0 overflow-hidden">
        <SignalsPanel
          activeSignals={activeSignals}
          weatherSignals={weatherSignals}
          onSimulateTrade={onSimulateTrade}
          isSimulating={isSimulating}
        />
        <div className="flex flex-col min-h-0 border-t border-neutral-800" style={{ height: '50%' }}>
          <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
            <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Trades</span>
            <span className="text-[10px] text-neutral-600 tabular-nums">{recentTrades.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0">
            <TradesTable trades={recentTrades} />
          </div>
        </div>
      </div>
    </div>
  )
}
