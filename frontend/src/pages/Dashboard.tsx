import { useState, useEffect, Suspense, lazy } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Link } from 'react-router-dom'
import {
  fetchDashboard, runScan, simulateTrade, startBot, stopBot,
  fetchSignalHistory, fetchBtcWindows, fetchTrades,
  fetchDecisions, fetchHealth, fetchCopyLeaderboard, fetchWeatherForecasts,
  fetchPolymarketMarkets, createWalletConfig, type PolymarketMarket,
} from '../api'
import type { SignalHistoryRow, ScoredTrader, DecisionLogRow, StrategyHealth } from '../api'
import { StatsCards } from '../components/StatsCards'
import { LoginModal } from '../components/LoginModal'
import { useAuth } from '../hooks/useAuth'
import { useStats } from '../hooks/useStats'
import { SignalsTable } from '../components/SignalsTable'
import { TradesTable } from '../components/TradesTable'
import { EquityChart } from '../components/EquityChart'
import { Terminal } from '../components/Terminal'
import { MicrostructurePanel } from '../components/MicrostructurePanel'
import { CalibrationPanel } from '../components/CalibrationPanel'
import { WeatherPanel } from '../components/WeatherPanel'
import { EdgeDistribution } from '../components/EdgeDistribution'
import { formatCountdown } from '../utils'
import type { BtcWindow } from '../types'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const GlobeView = lazy(() => import('../components/GlobeView').then(m => ({ default: m.GlobeView })))

// ── Shared Helpers ────────────────────────────────────────────────────────────

function LiveClock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])
  return (
    <span className="text-xs tabular-nums text-neutral-400">
      {time.toLocaleTimeString('en-US', { hour12: false })}
    </span>
  )
}

function WindowPill({ window: w }: { window: BtcWindow }) {
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

function RefreshBar({ interval }: { interval: number }) {
  const [progress, setProgress] = useState(100)
  useEffect(() => {
    setProgress(100)
    const step = 100 / (interval / 1000)
    const timer = setInterval(() => {
      setProgress(p => Math.max(0, p - step))
    }, 1000)
    return () => clearInterval(timer)
  }, [interval])
  return (
    <div className="refresh-bar w-16">
      <div className="refresh-fill" style={{ width: `${progress}%` }} />
    </div>
  )
}

// ── SignalsPanel (used in Overview tab) ───────────────────────────────────────

interface SignalsPanelProps {
  activeSignals: ReturnType<typeof Array.prototype.slice>
  weatherSignals: ReturnType<typeof Array.prototype.slice>
  onSimulateTrade: (ticker: string) => void
  isSimulating: boolean
}

function SignalsPanel({ activeSignals, weatherSignals, onSimulateTrade, isSimulating }: SignalsPanelProps) {
  const [tab, setTab] = useState<'live' | 'history'>('live')

  const { data: historyData } = useQuery({
    queryKey: ['signals-history'],
    queryFn: () => fetchSignalHistory({ limit: 100 }),
    enabled: tab === 'history',
    refetchInterval: tab === 'history' ? 30_000 : false,
  })

  const history: SignalHistoryRow[] = historyData?.items ?? []

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

// ── OVERVIEW TAB ──────────────────────────────────────────────────────────────

interface OverviewTabProps {
  data: Awaited<ReturnType<typeof fetchDashboard>>
  equityCurve: Awaited<ReturnType<typeof fetchDashboard>>['equity_curve']
  activeSignals: Awaited<ReturnType<typeof fetchDashboard>>['active_signals']
  recentTrades: Awaited<ReturnType<typeof fetchDashboard>>['recent_trades']
  weatherSignals: Awaited<ReturnType<typeof fetchDashboard>>['weather_signals']
  weatherForecasts: Awaited<ReturnType<typeof fetchDashboard>>['weather_forecasts']
  calibration: Awaited<ReturnType<typeof fetchDashboard>>['calibration']
  windows: BtcWindow[]
  micro: Awaited<ReturnType<typeof fetchDashboard>>['microstructure']
  onSimulateTrade: (ticker: string) => void
  isSimulating: boolean
  onStart: () => void
  onStop: () => void
  onScan: () => void
}

function OverviewTab({
  data: _data,
  equityCurve, activeSignals, recentTrades, weatherSignals,
  weatherForecasts, calibration, windows, micro,
  onSimulateTrade, isSimulating, onStart, onStop, onScan,
}: OverviewTabProps) {
  // Use unified stats hook for all stats (single source of truth)
  const stats = useStats()
  const actionableCount = activeSignals.filter(s => s.actionable).length + weatherSignals.filter(s => s.actionable).length

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
        <div className="border-b border-neutral-800" style={{ height: '25%', minHeight: '150px' }}>
          <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
            <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Equity</span>
            <span className={`text-[10px] tabular-nums ${stats.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {stats.pnl >= 0 ? '+' : ''}${stats.pnl.toFixed(0)}
            </span>
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

// ── TRADES TAB ────────────────────────────────────────────────────────────────

function TradesTab() {
  const [page, setPage] = useState(0)
  const [modeFilter, setModeFilter] = useState<string>('all')
  const [resultFilter, setResultFilter] = useState<string>('all')
  const [strategyFilter, setStrategyFilter] = useState<string>('all')
  const PER_PAGE = 50

  const { data: trades = [] } = useQuery({
    queryKey: ['trades-full'],
    queryFn: () => fetchTrades(),
    refetchInterval: 15_000,
  })

  const filtered = trades.filter(t => {
    if (modeFilter !== 'all' && (t as any).trading_mode !== modeFilter) return false
    if (resultFilter !== 'all' && (t as any).result !== resultFilter) return false
    if (strategyFilter !== 'all' && (t as any).strategy !== strategyFilter) return false
    return true
  })

  const strategies = Array.from(new Set(trades.map(t => (t as any).strategy).filter(Boolean)))
  const paginated = filtered.slice(page * PER_PAGE, (page + 1) * PER_PAGE)
  const totalPages = Math.ceil(filtered.length / PER_PAGE)

  const totalPnl = filtered.reduce((s, t) => s + ((t as any).pnl ?? 0), 0)
  const wins = filtered.filter(t => (t as any).result === 'win').length
  const losses = filtered.filter(t => (t as any).result === 'loss').length

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter row */}
      <div className="shrink-0 flex items-center gap-3 px-3 py-2 border-b border-neutral-800 bg-neutral-950">
        <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Filters</span>
        <select value={modeFilter} onChange={e => { setModeFilter(e.target.value); setPage(0) }} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Modes</option>
          <option value="paper">Paper</option>
          <option value="testnet">Testnet</option>
          <option value="live">Live</option>
        </select>
        <select value={resultFilter} onChange={e => { setResultFilter(e.target.value); setPage(0) }} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Results</option>
          <option value="pending">Pending</option>
          <option value="win">Win</option>
          <option value="loss">Loss</option>
        </select>
        <select value={strategyFilter} onChange={e => { setStrategyFilter(e.target.value); setPage(0) }} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Strategies</option>
          {strategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="flex-1" />
        <span className="text-[10px] text-neutral-600 tabular-nums">{filtered.length} trades</span>
      </div>

      {/* Summary bar */}
      <div className="shrink-0 flex items-center gap-6 px-3 py-1.5 border-b border-neutral-800 bg-neutral-950/50">
        <span className="text-[10px] text-neutral-500">Total: <span className="text-neutral-200 tabular-nums">{filtered.length}</span></span>
        <span className="text-[10px] text-neutral-500">Wins: <span className="text-green-500 tabular-nums">{wins}</span></span>
        <span className="text-[10px] text-neutral-500">Losses: <span className="text-red-500 tabular-nums">{losses}</span></span>
        <span className="text-[10px] text-neutral-500">PNL: <span className={`tabular-nums font-semibold ${totalPnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}</span></span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-neutral-950">
            <tr className="border-b border-neutral-800">
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Time</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Market</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Dir</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">Size</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">Entry</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">PNL</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Result</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Mode</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {paginated.map((t: any) => (
              <tr key={t.id} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                <td className="px-2 py-1 text-neutral-600 whitespace-nowrap">
                  {t.timestamp ? new Date(t.timestamp).toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'}
                </td>
                <td className="px-2 py-1 text-neutral-400 truncate max-w-[100px]" title={t.market_ticker}>
                  {t.market_ticker?.length > 18 ? `${t.market_ticker.slice(0, 16)}…` : t.market_ticker ?? '—'}
                </td>
                <td className={`px-2 py-1 font-bold ${t.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                  {t.direction?.toUpperCase() ?? '—'}
                </td>
                <td className="px-2 py-1 text-neutral-300 text-right tabular-nums">${(t.size ?? 0).toFixed(0)}</td>
                <td className="px-2 py-1 text-neutral-500 text-right tabular-nums">{t.entry_price != null ? `${(t.entry_price * 100).toFixed(1)}c` : '—'}</td>
                <td className={`px-2 py-1 text-right tabular-nums ${(t.pnl ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                </td>
                <td className="px-2 py-1">
                  {t.result === 'win' ? <span className="text-green-500">win</span>
                    : t.result === 'loss' ? <span className="text-red-500">loss</span>
                    : <span className="text-neutral-600">pending</span>}
                </td>
                <td className="px-2 py-1">
                  {t.trading_mode === 'live' ? <span className="text-red-400 text-[9px] uppercase">live</span>
                    : t.trading_mode === 'testnet' ? <span className="text-yellow-400 text-[9px] uppercase">testnet</span>
                    : <span className="text-amber-400 text-[9px] uppercase">paper</span>}
                </td>
                <td className="px-2 py-1 text-neutral-600">{t.strategy ?? '—'}</td>
              </tr>
            ))}
            {paginated.length === 0 && (
              <tr><td colSpan={9} className="px-2 py-6 text-center text-neutral-700">No trades found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="shrink-0 flex items-center justify-center gap-3 py-2 border-t border-neutral-800">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} className="px-2 py-0.5 border border-neutral-700 text-neutral-400 text-[10px] disabled:opacity-40 hover:border-neutral-500 transition-colors">Prev</button>
          <span className="text-[10px] text-neutral-600">{page + 1} / {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} className="px-2 py-0.5 border border-neutral-700 text-neutral-400 text-[10px] disabled:opacity-40 hover:border-neutral-500 transition-colors">Next</button>
        </div>
      )}
    </div>
  )
}

// ── SIGNALS TAB ───────────────────────────────────────────────────────────────

function SignalsTab() {
  const [dirFilter, setDirFilter] = useState<string>('all')
  const [execFilter, setExecFilter] = useState<string>('all')

  const { data } = useQuery({
    queryKey: ['signal-history-tab'],
    queryFn: () => fetchSignalHistory({ limit: 200 }),
    refetchInterval: 30_000,
  })

  const rows: SignalHistoryRow[] = data?.items ?? []
  const filtered = rows.filter(r => {
    if (dirFilter !== 'all' && r.direction !== dirFilter) return false
    if (execFilter === 'yes' && !r.executed) return false
    if (execFilter === 'no' && r.executed) return false
    return true
  })

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-center gap-3 px-3 py-2 border-b border-neutral-800 bg-neutral-950">
        <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Filters</span>
        <select value={dirFilter} onChange={e => setDirFilter(e.target.value)} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Directions</option>
          <option value="up">Up</option>
          <option value="down">Down</option>
        </select>
        <select value={execFilter} onChange={e => setExecFilter(e.target.value)} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All</option>
          <option value="yes">Executed</option>
          <option value="no">Skipped</option>
        </select>
        <div className="flex-1" />
        <span className="text-[10px] text-neutral-600 tabular-nums">{filtered.length} signals</span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-neutral-950">
            <tr className="border-b border-neutral-800">
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Time</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Market</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Dir</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">Edge%</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">Conf%</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Executed</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={`border-b border-neutral-800/40 hover:bg-neutral-900/30 ${row.executed ? 'bg-green-500/5' : ''}`}>
                <td className="px-2 py-1 text-neutral-600 whitespace-nowrap">
                  {row.timestamp ? new Date(row.timestamp).toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'}
                </td>
                <td className="px-2 py-1 text-neutral-400 truncate max-w-[100px]" title={row.market_ticker}>
                  {row.market_ticker.length > 18 ? `${row.market_ticker.slice(0, 16)}…` : row.market_ticker}
                </td>
                <td className={`px-2 py-1 font-bold ${row.direction === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                  {row.direction?.toUpperCase()}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-neutral-300">
                  {row.edge != null ? `${(row.edge * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-neutral-500">
                  {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="px-2 py-1">
                  <span className={row.executed ? 'text-green-500' : 'text-neutral-700'}>{row.executed ? 'yes' : 'no'}</span>
                </td>
                <td className="px-2 py-1">
                  {row.outcome_correct == null ? <span className="text-neutral-700">pending</span>
                    : row.outcome_correct ? <span className="text-green-500">win</span>
                    : <span className="text-red-500">loss</span>}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-2 py-6 text-center text-neutral-700">No signals found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── MARKETS TAB ───────────────────────────────────────────────────────────────

function MarketsTab() {
  const { data: btcWindows = [] } = useQuery({
    queryKey: ['btc-windows-tab'],
    queryFn: fetchBtcWindows,
    refetchInterval: 10_000,
  })
  const { data: weatherForecasts = [] } = useQuery({
    queryKey: ['weather-forecasts-tab'],
    queryFn: fetchWeatherForecasts,
    refetchInterval: 30_000,
  })

  // Polymarket markets - fetch all (no pagination)
  const { data: polymarketMarkets = [], isLoading: pmLoading } = useQuery({
    queryKey: ['polymarket-markets-all'],
    queryFn: () => fetchPolymarketMarkets(0, 5000), // Fetch up to 5000 markets
    refetchInterval: 60_000,
  })

  return (
    <div className="grid grid-cols-3 gap-0 h-full min-h-0 divide-x divide-neutral-800">
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
                  <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{(w as any).volume != null ? `$${((w as any).volume / 1000).toFixed(0)}k` : '—'}</td>
                  <td className="px-3 py-1 text-right text-neutral-500 tabular-nums">{formatCountdown(w.time_until_end)}</td>
                </tr>
              ))}
              {btcWindows.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-neutral-700">No BTC windows</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Weather Markets */}
      <div className="flex flex-col min-h-0">
        <div className="px-3 py-2 border-b border-neutral-800 shrink-0 flex items-center justify-between">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Weather Markets</span>
          <span className="text-[9px] text-neutral-600">auto-refresh 30s</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-neutral-950">
              <tr className="border-b border-neutral-800">
                <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">City</th>
                <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Target</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">High</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Low</th>
                <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {(weatherForecasts as any[]).map((f: any, i: number) => (
                <tr key={i} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                  <td className="px-3 py-1 text-neutral-300">{f.city ?? f.location ?? '—'}</td>
                  <td className="px-3 py-1 text-neutral-500">{f.target_date ?? f.date ?? '—'}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-red-400">{f.mean_high != null ? `${f.mean_high.toFixed(1)}°` : '—'}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-blue-400">{f.mean_low != null ? `${f.mean_low.toFixed(1)}°` : '—'}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-neutral-400">{f.ensemble_agreement != null ? `${(f.ensemble_agreement * 100).toFixed(0)}%` : '—'}</td>
                </tr>
              ))}
              {weatherForecasts.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-neutral-700">No weather forecasts</td></tr>}
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

// ── LEADERBOARD TAB ───────────────────────────────────────────────────────────

function LeaderboardTab() {
  const { data: leaders = [], isError } = useQuery({
    queryKey: ['copy-leaderboard-tab'],
    queryFn: fetchCopyLeaderboard,
    retry: false,
  })

  const queryClient = useQueryClient()
  const [copyingWallet, setCopyingWallet] = useState<string | null>(null)
  const [copySuccess, setCopySuccess] = useState<string | null>(null)
  const [copyError, setCopyError] = useState<string | null>(null)

  const sorted = [...leaders].sort((a, b) => b.score - a.score)

  const handleCopyTrade = async (trader: ScoredTrader) => {
    setCopyingWallet(trader.wallet)
    setCopySuccess(null)
    setCopyError(null)

    try {
      await createWalletConfig({
        address: trader.wallet,
        pseudonym: trader.pseudonym || undefined,
        source: 'leaderboard',
        enabled: true,
      })
      setCopySuccess(trader.wallet)
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['copy-trader-status'] })
      queryClient.invalidateQueries({ queryKey: ['wallets-config'] })
    } catch (err: any) {
      setCopyError(trader.wallet)
      console.error('Failed to copy trader:', err)
    } finally {
      setCopyingWallet(null)
      // Clear success message after 3 seconds
      if (copySuccess) {
        setTimeout(() => setCopySuccess(null), 3000)
      }
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Trader Leaderboard</span>
        <span className="text-[10px] text-neutral-600 tabular-nums">{sorted.length} traders</span>
      </div>
      {isError && (
        <div className="px-3 py-2 text-[10px] text-amber-600/70 border-b border-neutral-800">
          Auth required — log in as admin to view leaderboard
        </div>
      )}
      <div className="flex-1 overflow-y-auto min-h-0">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-neutral-950">
            <tr className="border-b border-neutral-800">
              <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Rank</th>
              <th className="text-left px-3 py-1 text-neutral-600 uppercase tracking-wider">Trader</th>
              <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Profit 30d</th>
              <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Win Rate</th>
              <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Trades</th>
              <th className="text-right px-3 py-1 text-neutral-600 uppercase tracking-wider">Score</th>
              <th className="text-center px-3 py-1 text-neutral-600 uppercase tracking-wider">Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t: ScoredTrader, i: number) => (
              <tr key={t.wallet} className="border-b border-neutral-800/40 hover:bg-neutral-900/30" title={t.wallet}>
                <td className="px-3 py-1 text-neutral-500 tabular-nums">#{i + 1}</td>
                <td className="px-3 py-1 text-neutral-300">{t.pseudonym || `${t.wallet.slice(0, 8)}…${t.wallet.slice(-6)}`}</td>
                <td className={`px-3 py-1 text-right tabular-nums ${t.profit_30d >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {t.profit_30d >= 0 ? '+' : ''}${t.profit_30d.toFixed(0)}
                </td>
                <td className="px-3 py-1 text-right tabular-nums text-neutral-400">{(t.win_rate * 100).toFixed(1)}%</td>
                <td className="px-3 py-1 text-right tabular-nums text-neutral-500">{t.total_trades}</td>
                <td className="px-3 py-1 text-right tabular-nums text-amber-400 font-semibold">{t.score.toFixed(2)}</td>
                <td className="px-3 py-1 text-center">
                  {copySuccess === t.wallet ? (
                    <span className="text-[9px] text-green-500">✓ Copied</span>
                  ) : copyError === t.wallet ? (
                    <span className="text-[9px] text-red-500">Failed</span>
                  ) : (
                    <button
                      onClick={() => handleCopyTrade(t)}
                      disabled={copyingWallet === t.wallet}
                      className="text-[9px] px-2 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 disabled:opacity-50 disabled:cursor-not-allowed border border-amber-500/30 rounded"
                    >
                      {copyingWallet === t.wallet ? 'Copying...' : 'Copy Trade'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {sorted.length === 0 && !isError && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-neutral-700">No leaderboard data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── DECISIONS TAB ─────────────────────────────────────────────────────────────

function DecisionsTab() {
  const [stratFilter, setStratFilter] = useState<string>('all')
  const [decisionFilter, setDecisionFilter] = useState<string>('all')

  const { data } = useQuery({
    queryKey: ['decisions-tab'],
    queryFn: () => fetchDecisions({ limit: 100 }),
    refetchInterval: 20_000,
  })

  const rows: DecisionLogRow[] = data?.items ?? []
  const strategies = Array.from(new Set(rows.map(r => r.strategy).filter(Boolean)))
  const filtered = rows.filter(r => {
    if (stratFilter !== 'all' && r.strategy !== stratFilter) return false
    if (decisionFilter !== 'all' && r.decision !== decisionFilter) return false
    return true
  })

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-center gap-3 px-3 py-2 border-b border-neutral-800 bg-neutral-950">
        <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Filters</span>
        <select value={stratFilter} onChange={e => setStratFilter(e.target.value)} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Strategies</option>
          {strategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={decisionFilter} onChange={e => setDecisionFilter(e.target.value)} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:outline-none">
          <option value="all">All Decisions</option>
          <option value="BUY">BUY</option>
          <option value="SKIP">SKIP</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
        <div className="flex-1" />
        <span className="text-[10px] text-neutral-600 tabular-nums">{filtered.length} decisions</span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-neutral-950">
            <tr className="border-b border-neutral-800">
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Time</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Strategy</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Market</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Decision</th>
              <th className="text-right px-2 py-1 text-neutral-600 uppercase tracking-wider">Conf</th>
              <th className="text-left px-2 py-1 text-neutral-600 uppercase tracking-wider">Reason</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r: DecisionLogRow) => (
              <tr key={r.id} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                <td className="px-2 py-1 text-neutral-600 whitespace-nowrap">
                  {r.created_at ? new Date(r.created_at).toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'}
                </td>
                <td className="px-2 py-1 text-neutral-500">{r.strategy}</td>
                <td className="px-2 py-1 text-neutral-400 truncate max-w-[80px]" title={r.market_ticker}>
                  {r.market_ticker.length > 14 ? `${r.market_ticker.slice(0, 12)}…` : r.market_ticker}
                </td>
                <td className="px-2 py-1">
                  {r.decision === 'BUY' ? <span className="text-green-400 font-bold">BUY</span>
                    : r.decision === 'SKIP' ? <span className="text-neutral-500">SKIP</span>
                    : r.decision === 'SELL' ? <span className="text-red-400 font-bold">SELL</span>
                    : <span className="text-neutral-400">{r.decision}</span>}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-neutral-500">
                  {r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="px-2 py-1 text-neutral-600 truncate max-w-[200px]" title={r.reason ?? ''}>
                  {r.reason ?? '—'}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="px-2 py-6 text-center text-neutral-700">No decisions found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── PERFORMANCE TAB ───────────────────────────────────────────────────────────

function PerformanceTab() {
  // Use unified stats hook (single source of truth)
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

  // Build win rate chart data (from raw trades for paper/live breakdown)
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

  // Daily PNL approximation
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
            { label: 'Win Rate', value: `${(winRate * 100).toFixed(1)}%`, color: winRate >= 0.5 ? 'text-green-500' : 'text-amber-400' },
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
            <div className="text-[10px] text-neutral-700 py-2">No strategy health data</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── MAIN DASHBOARD ────────────────────────────────────────────────────────────

const DASHBOARD_TABS = ['Overview', 'Trades', 'Signals', 'Markets', 'Leaderboard', 'Decisions', 'Performance'] as const
type DashboardTab = typeof DASHBOARD_TABS[number]

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { isAuthenticated, authRequired, login, logout } = useAuth()
  const [showLogin, setShowLogin] = useState(false)
  const [activeTab, setActiveTab] = useState<DashboardTab>('Overview')

  // Use unified stats hook as single source of truth
  const unifiedStats = useStats()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 10000,
  })

  const scanMutation = useMutation({
    mutationFn: runScan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['stats-unified'] })
    },
  })

  const tradeMutation = useMutation({
    mutationFn: simulateTrade,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['stats-unified'] })
    },
  })

  const startMutation = useMutation({
    mutationFn: startBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['stats-unified'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['stats-unified'] })
    },
  })

  const activeSignals = data?.active_signals ?? []
  const recentTrades = data?.recent_trades ?? []
  const btcPrice = data?.btc_price
  const micro = data?.microstructure
  const windows = data?.windows ?? []
  const weatherSignals = data?.weather_signals ?? []
  const weatherForecasts = data?.weather_forecasts ?? []

  const stats = data?.stats ?? {
    is_running: false,
    last_run: null,
    total_trades: 0,
    total_pnl: 0,
    bankroll: 10000,
    winning_trades: 0,
    win_rate: 0
  }
  const equityCurve = data?.equity_curve ?? []
  const calibration = data?.calibration ?? null

  if (isLoading) {
    return (
      <div className="h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-10 h-10 mx-auto mb-4">
            <div className="absolute inset-0 border-2 border-neutral-800 rounded-full" />
            <div className="absolute inset-0 border-2 border-transparent border-t-green-500 rounded-full animate-spin" />
          </div>
          <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-mono">Initializing</div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-500 text-xs uppercase mb-2 tracking-wider">Connection Error</div>
          <button onClick={() => refetch()} className="px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen bg-black text-neutral-200 flex flex-col overflow-hidden">
      {/* NAVBAR */}
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="shrink-0 border-b border-neutral-800 px-3 py-1.5 flex items-center gap-4 relative"
      >
        <div className="scan-line" />
        <div className="flex items-center gap-2 shrink-0">
          <Link to="/admin" className="text-[9px] text-neutral-600 hover:text-green-500 uppercase tracking-wider transition-colors mr-1">Admin</Link>
          <h1 className="text-xs font-bold text-neutral-100 uppercase tracking-widest whitespace-nowrap font-mono">TRADING TERMINAL</h1>
          <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase ${unifiedStats.isRunning ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-neutral-800 text-neutral-500 border border-neutral-700'}`}>
            {unifiedStats.isRunning ? 'Live' : 'Idle'}
          </span>
          {(() => {
            const mode = (stats as any).trading_mode || 'paper'
            const cfg: Record<string, { label: string; cls: string }> = {
              paper: { label: 'Paper', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
              testnet: { label: 'Testnet', cls: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
              live: { label: 'LIVE', cls: 'bg-red-500/10 text-red-500 border-red-500/20' },
            }
            const { label, cls } = cfg[mode] || cfg['paper']
            return <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase border ${cls}`}>{label}</span>
          })()}
        </div>

        {btcPrice && (
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-sm font-bold tabular-nums text-neutral-100">${btcPrice.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            <span className={`text-[10px] tabular-nums ${btcPrice.change_24h >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {btcPrice.change_24h >= 0 ? '+' : ''}{btcPrice.change_24h.toFixed(2)}%
            </span>
          </div>
        )}

        <div className="flex-1" />
        <StatsCards />

        <div className="flex items-center gap-2 shrink-0">
          {authRequired && (
            isAuthenticated ? (
              <button onClick={logout} className="px-2 py-1 text-[9px] text-neutral-600 border border-neutral-800 hover:border-neutral-700 hover:text-neutral-400 uppercase tracking-wider transition-colors">Logout</button>
            ) : (
              <button onClick={() => setShowLogin(true)} className="px-2 py-1 text-[9px] text-neutral-500 border border-neutral-700 hover:border-green-500/40 hover:text-green-400 uppercase tracking-wider transition-colors">Login</button>
            )
          )}
          <LiveClock />
        </div>

        <AnimatePresence>
          {showLogin && (
            <LoginModal login={login} onSuccess={() => setShowLogin(false)} onCancel={() => setShowLogin(false)} />
          )}
        </AnimatePresence>
      </motion.header>

      {/* TAB BAR */}
      <div className="shrink-0 border-b border-neutral-800 px-3 flex items-center gap-0">
        {DASHBOARD_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 text-[10px] uppercase tracking-wider border-b-2 transition-colors ${
              activeTab === tab
                ? 'text-green-500 border-green-500'
                : 'text-neutral-500 border-transparent hover:text-neutral-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* TAB CONTENT */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {activeTab === 'Overview' && (
          <OverviewTab
            data={data}
            equityCurve={equityCurve}
            activeSignals={activeSignals}
            recentTrades={recentTrades}
            weatherSignals={weatherSignals}
            weatherForecasts={weatherForecasts}
            calibration={calibration}
            windows={windows}
            micro={micro ?? null}
            onSimulateTrade={(ticker) => tradeMutation.mutate(ticker)}
            isSimulating={tradeMutation.isPending}
            onStart={() => startMutation.mutate()}
            onStop={() => stopMutation.mutate()}
            onScan={() => scanMutation.mutate()}
          />
        )}
        {activeTab === 'Trades' && <TradesTab />}
        {activeTab === 'Signals' && <SignalsTab />}
        {activeTab === 'Markets' && <MarketsTab />}
        {activeTab === 'Leaderboard' && <LeaderboardTab />}
        {activeTab === 'Decisions' && <DecisionsTab />}
        {activeTab === 'Performance' && <PerformanceTab />}
      </div>

      {/* FOOTER */}
      <footer className="shrink-0 border-t border-neutral-800 px-3 py-0.5 flex items-center justify-between">
        <span className="text-[10px] text-neutral-700 font-mono">Binance/Coinbase | Open-Meteo | Polymarket + Kalshi</span>
        <div className="flex items-center gap-3">
          <RefreshBar interval={10000} />
          <span className="text-[10px] text-neutral-700 font-mono">Copy · Weather · Kalshi · BTC Oracle · BTC 5m</span>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span className="text-[10px] text-neutral-600 font-mono">Connected</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
