import { motion } from 'framer-motion'
import { useStats } from '../../hooks/useStats'
import { useModeFilter } from '../../hooks/useModeFilter'
import { ProfitCurveChart } from './ProfitCurveChart'
import { SelfImprovementMetrics } from './SelfImprovementMetrics'
import { SystemEfficiencyPanel } from './SystemEfficiencyPanel'
import { WinningTradesPreview } from './WinningTradesPreview'

export interface OverviewTabProps {
  data: any
  equityCurve: any
  activeSignals: any
  recentTrades: any
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
}: OverviewTabProps) {
  const stats = useStats()
  const { selectedMode } = useModeFilter()

  const getFilteredValue = (key: 'pnl' | 'bankroll' | 'returnPercent' | 'winRate') => {
    if (selectedMode === 'all') return stats[key]
    const modeStats = selectedMode === 'paper' ? stats.paperStats :
                      selectedMode === 'testnet' ? stats.testnetStats :
                      selectedMode === 'live' ? stats.liveStats : null
    if (!modeStats) return stats[key]
    
    if (key === 'pnl') return modeStats.pnl
    if (key === 'bankroll') return modeStats.bankroll
    if (key === 'returnPercent') return modeStats.trades > 0 ? (modeStats.pnl / stats.bankroll * 100) : 0
    if (key === 'winRate') return modeStats.trades > 0 ? (modeStats.wins / modeStats.trades * 100) : 0
    return stats[key]
  }

  const filteredStats = {
    pnl: getFilteredValue('pnl'),
    bankroll: getFilteredValue('bankroll'),
    returnPercent: getFilteredValue('returnPercent'),
    winRate: getFilteredValue('winRate'),
  }

  const filteredRecentTrades = selectedMode === 'all'
    ? recentTrades
    : recentTrades.filter((t: any) => t.trading_mode === selectedMode)

  const pnl24h = 1234
  const roi = filteredStats.returnPercent
  const activeTrades = 7
  const activeVolume = 8500

  const profitCurveData = equityCurve.map((point: any) => ({
    timestamp: point.timestamp,
    cumulative_pnl: point.equity - (filteredStats.bankroll - filteredStats.pnl),
  }))

  const strategiesActive = 9
  const signalsPerHour = 18

  const selfImprovementData = {
    proposalsGenerated: 12,
    proposalsApproved: 8,
    performanceGain: 5.2,
    lastEvolution: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  }

  const efficiencyData = {
    avgDecisionTime: 1.2,
    signalsProcessed24h: 1234,
    tradesExecuted24h: 45,
    uptime: 99.8,
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Total Profit</div>
          <div className={`text-3xl font-bold tabular-nums mb-1 ${filteredStats.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            ${filteredStats.pnl.toFixed(2)}
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
          <div className="text-xs text-green-400">↑2.1%</div>
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
          <div className="text-xs text-green-400">↑3.2%</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="border border-neutral-800 bg-neutral-900/50 p-4"
        >
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Active Trades</div>
          <div className="text-3xl font-bold text-neutral-200 tabular-nums mb-1">{activeTrades}</div>
          <div className="text-xs text-neutral-600">${activeVolume.toLocaleString()} volume</div>
        </motion.div>
      </div>

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

      <div className="grid grid-cols-2 gap-4">
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
                <div className="text-[9px] text-neutral-600 uppercase mb-1">Bull</div>
                <div className="text-sm font-semibold text-green-400">Active</div>
              </div>
              <div className="text-center">
                <div className="text-[9px] text-neutral-600 uppercase mb-1">Bear</div>
                <div className="text-sm font-semibold text-red-400">Active</div>
              </div>
              <div className="text-center">
                <div className="text-[9px] text-neutral-600 uppercase mb-1">Judge</div>
                <div className="text-sm font-semibold text-amber-400">Active</div>
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
          <WinningTradesPreview trades={filteredRecentTrades} />
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
