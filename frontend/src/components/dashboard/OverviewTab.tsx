import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useStats } from '../../hooks/useStats'
import { useModeFilter } from '../../hooks/useModeFilter'
import { ProfitCurveChart } from './ProfitCurveChart'
import { SelfImprovementMetrics } from './SelfImprovementMetrics'
import { SystemEfficiencyPanel } from './SystemEfficiencyPanel'
import { WinningTradesPreview } from './WinningTradesPreview'
import { adminApi, api } from '../../api'
import type { BotStats, PnlModeStats, Trade } from '../../types'

export interface OverviewTabProps {
  data: any
  equityCurve: any
  activeSignals: any
  recentTrades: any
  topWinningTrades?: any[]
  weatherSignals: any
  weatherForecasts: any
  calibration: any
  windows: any[]
  micro: any
  onSimulateTrade: (ticker: string) => void
  isSimulating: boolean
  onStart: () => void
  onStop: () => void
  onScan: () => void
}

export function OverviewTab({
  equityCurve,
  recentTrades,
  topWinningTrades = [],
  activeSignals,
}: OverviewTabProps) {
  const stats = useStats()
  const { selectedMode } = useModeFilter()

  const { data: proposalsData } = useQuery({
    queryKey: ['proposals'],
    queryFn: async () => {
      try {
        const response = await adminApi.get('/proposals')
        return response.data
      } catch (error) {
        return []
      }
    },
    refetchInterval: 30000,
  })

  const { data: healthData } = useQuery({
    queryKey: ['health-detailed'],
    queryFn: async () => {
      try {
        const response = await api.get('/health/detailed')
        return response.data
      } catch { return null }
    },
    refetchInterval: 30000,
  })

  const getFilteredValue = (key: 'pnl' | 'bankroll' | 'returnPercent' | 'winRate') => {
    if (selectedMode === 'all') return stats[key]
    const modeStats = selectedMode === 'paper' ? stats.paperStats :
                      selectedMode === 'testnet' ? stats.testnetStats :
                      selectedMode === 'live' ? stats.liveStats : null
    if (!modeStats) return stats[key]
    
    if (key === 'pnl') return modeStats.pnl ?? 0
    if (key === 'bankroll') return modeStats.bankroll ?? 0
    if (key === 'returnPercent') {
      const initialBankroll = modeStats.initial_bankroll ?? stats.stats.initial_bankroll
      return initialBankroll > 0 ? (modeStats.pnl / initialBankroll * 100) : 0
    }
    if (key === 'winRate') return modeStats.trades > 0 ? (modeStats.wins / modeStats.trades * 100) : 0
    return stats[key]
  }

  const pnl = getFilteredValue('pnl')
  const bankroll = getFilteredValue('bankroll')
  const returnPercent = getFilteredValue('returnPercent')
  const winRate = getFilteredValue('winRate')

  const filteredStats = {
    pnl,
    bankroll,
    returnPercent,
    winRate
  }

  const filteredRecentTrades = selectedMode === 'all'
    ? recentTrades
    : recentTrades.filter((t: any) => t.trading_mode === selectedMode)

  const filteredWinningTrades = selectedMode === 'all'
    ? topWinningTrades
    : topWinningTrades.filter((t: any) => t.trading_mode === selectedMode)
  const settledLossTrades = (filteredRecentTrades as Trade[])
    .filter(t => (t.pnl ?? 0) < 0)
    .sort((a, b) => (a.pnl ?? 0) - (b.pnl ?? 0))
  const sourceStats = stats.stats as BotStats
  const activeMode = sourceStats.mode ?? 'paper'
  const liveStats = sourceStats.live
  const paperStats = sourceStats.paper
  const testnetStats = sourceStats.testnet

  const formatMoney = (value: number | undefined | null) => `${(value ?? 0) >= 0 ? '+' : '-'}$${Math.abs(value ?? 0).toFixed(2)}`
  const modeCard = (label: string, modeStats: PnlModeStats | undefined, accent: string) => ({
    label,
    pnl: modeStats?.pnl ?? 0,
    bankroll: modeStats?.bankroll ?? 0,
    trades: modeStats?.trades ?? 0,
    openTrades: modeStats?.open_trades ?? 0,
    accent,
  })
  const modeCards = [
    modeCard('Live account', liveStats, 'text-red-400'),
    modeCard('Paper learning', paperStats, 'text-amber-400'),
    modeCard('Testnet', testnetStats, 'text-yellow-400'),
  ]
  
  const trades24h = filteredRecentTrades.filter((t: any) => {
    const tradeTime = new Date(t.timestamp).getTime()
    const now = Date.now()
    return (now - tradeTime) < 24 * 60 * 60 * 1000
  })
  const pnl24h = trades24h.reduce((sum: number, t: any) => sum + (t.pnl ?? 0), 0)
  
  const roi = filteredStats.returnPercent
  const activeTrades = stats.openTrades || 0
  const activeVolume = stats.openExposure || 0

  const profitCurveData = equityCurve.map((point: any) => ({
    timestamp: point.timestamp,
    cumulative_pnl: point.pnl,
  }))

  // Count active strategies from data
  const strategiesActive = activeSignals?.length || 0
  const signalsPerHour = Math.round((activeSignals?.length || 0) * 2)

  const proposalsGenerated = proposalsData?.length || 0
  const proposalsApproved = proposalsData?.filter((p: any) => p.admin_decision === 'approved').length || 0
  const lastProposal = proposalsData?.[0]
  
  const selfImprovementData = {
    proposalsGenerated,
    proposalsApproved,
    performanceGain: proposalsApproved > 0 ? ((proposalsApproved / proposalsGenerated) * 100) : 0,
    lastEvolution: lastProposal?.created_at || null,
  }

  const efficiencyData = {
    avgDecisionTime: healthData?.avg_signal_time_ms ? healthData.avg_signal_time_ms / 1000 : -1,
    signalsProcessed24h: activeSignals?.length || 0,
    tradesExecuted24h: trades24h.length,
    uptime: healthData?.uptime_seconds ? Math.min(healthData.uptime_seconds / (30 * 24 * 3600) * 100, 100) : -1,
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      {/* Hero Stats Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Total Profit</div>
          <div className={`text-3xl font-bold tabular-nums mb-1 ${filteredStats.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            {filteredStats.pnl >= 0 ? '+' : '-'}${Math.abs(filteredStats.pnl).toFixed(2)}
          </div>
          <div className="text-xs text-neutral-600">
            <span className={pnl24h >= 0 ? 'text-green-400' : 'text-red-400'}>
              {pnl24h >= 0 ? '+' : ''}${pnl24h.toFixed(2)}
            </span> 24h
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Win Rate</div>
          <div className="text-3xl font-bold text-neutral-200 tabular-nums mb-1">
            {filteredStats.winRate.toFixed(1)}%
          </div>
          <div className="text-xs text-neutral-600">All time</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">ROI</div>
          <div className={`text-3xl font-bold tabular-nums mb-1 ${roi >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            {roi >= 0 ? '+' : ''}{roi.toFixed(1)}%
          </div>
          <div className="text-xs text-neutral-600">vs initial</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Active Trades</div>
          <div className="text-3xl font-bold text-neutral-200 tabular-nums mb-1">{activeTrades}</div>
          <div className="text-xs text-neutral-600">${activeVolume.toFixed(2)} volume</div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45 }}
        className="grid grid-cols-1 lg:grid-cols-4 gap-4"
      >
        <div className="border border-cyan-500/20 bg-cyan-500/[0.04] p-4 lg:col-span-1">
          <div className="text-[10px] text-cyan-300 uppercase tracking-wider mb-2">PNL Source</div>
          <div className="text-sm text-neutral-200 font-semibold mb-1 uppercase">{selectedMode === 'all' ? 'Consolidated view' : `${selectedMode} mode`}</div>
          <p className="text-[11px] leading-5 text-neutral-500">
            The headline can show live account equity while paper/testnet trades are losing. Loss rows are preserved in the Trades tab; this panel separates the sources.
          </p>
          <div className="mt-3 text-[10px] text-neutral-600">
            Active engine: <span className="text-neutral-300 uppercase">{activeMode}</span>
          </div>
        </div>

        {modeCards.map(card => (
          <div key={card.label} className="border border-neutral-800 bg-neutral-900/50 p-4">
            <div className={`text-[10px] uppercase tracking-wider mb-2 ${card.accent}`}>{card.label}</div>
            <div className={`text-2xl font-bold tabular-nums mb-1 ${card.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatMoney(card.pnl)}</div>
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-neutral-800 text-[10px]">
              <div>
                <div className="text-neutral-600 uppercase">Bankroll</div>
                <div className="text-neutral-300 tabular-nums">${card.bankroll.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-neutral-600 uppercase">Trades</div>
                <div className="text-neutral-300 tabular-nums">{card.trades}</div>
              </div>
              <div>
                <div className="text-neutral-600 uppercase">Open</div>
                <div className="text-neutral-300 tabular-nums">{card.openTrades}</div>
              </div>
            </div>
          </div>
        ))}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="border border-neutral-800 bg-neutral-900/50 p-4"
        style={{ height: '300px' }}
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-neutral-400 uppercase tracking-wider">30-Day Profit Curve</span>
          <span className="text-xs text-neutral-600">Interactive</span>
        </div>
        <div style={{ height: 'calc(100% - 32px)' }}>
          <ProfitCurveChart data={profitCurveData} />
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-neutral-400 uppercase tracking-wider">AI Decision Engine</span>
            <span className="px-2 py-0.5 text-[9px] font-bold uppercase bg-green-500/10 text-green-400 border border-green-500/20">
              Active
            </span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500">Strategies Active</span>
              <span className="text-lg font-bold text-neutral-200">{strategiesActive}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500">Signals/Hour</span>
              <span className="text-lg font-bold text-cyan-400">{signalsPerHour}</span>
            </div>
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-neutral-800">
              <div className="text-center">
                <div className="text-[9px] text-neutral-600 uppercase mb-1">Signals</div>
                <div className="text-sm font-semibold text-cyan-400">{activeSignals?.length || 0}</div>
              </div>
              <div className="text-center">
                <div className="text-[9px] text-neutral-600 uppercase mb-1">24h Trades</div>
                <div className="text-sm font-semibold text-neutral-200">{trades24h.length}</div>
              </div>
              <div className="text-center">
                <div className="text-[9px] text-neutral-600 uppercase mb-1">Open</div>
                <div className="text-sm font-semibold text-amber-400">{activeTrades}</div>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          className="border border-neutral-800 bg-neutral-900/50"
          style={{ height: '280px' }}
        >
          <WinningTradesPreview trades={filteredWinningTrades.length > 0 ? filteredWinningTrades : filteredRecentTrades} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.75 }}
          className="border border-neutral-800 bg-neutral-900/50"
          style={{ height: '280px' }}
        >
          <WinningTradesPreview
            trades={settledLossTrades.length > 0 ? settledLossTrades : filteredRecentTrades}
            title="Worst Loss Trades"
            variant="losses"
          />
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.8 }}
        className="border border-neutral-800 bg-neutral-900/50 p-4"
      >
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm text-neutral-400 uppercase tracking-wider">Self-Improvement Metrics</span>
          <span className="text-[9px] text-neutral-600 uppercase">AI Evolution</span>
        </div>
        <SelfImprovementMetrics {...selfImprovementData} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.9 }}
        className="border border-neutral-800 bg-neutral-900/50 p-4"
      >
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm text-neutral-400 uppercase tracking-wider">System Efficiency</span>
          <span className="text-[9px] text-neutral-600 uppercase">Performance</span>
        </div>
        <SystemEfficiencyPanel {...efficiencyData} />
      </motion.div>
    </div>
  )
}
