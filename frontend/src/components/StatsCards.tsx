import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { fetchDashboard } from '../api'
import { LineChart, Line, ResponsiveContainer } from 'recharts'
import { useStats } from '../hooks/useStats'

export function StatsCards() {
  const { pnl, wins, trades, bankroll, winRate, returnPercent, mode, isRunning, openExposure, openTrades, totalEquity } = useStats()
  const modeLabel = mode ? mode.toUpperCase() : ''

  const { data, isLoading, isError } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 10000,
    staleTime: 5000
  })

  const equityCurve = (isLoading || isError) ? [] : (data?.equity_curve ?? [])

  return (
    <div className="flex items-center gap-3">
      {modeLabel && (
        <>
          <span className={`text-[9px] font-bold uppercase tracking-wider px-1 ${
            mode === 'paper' ? 'text-neutral-500 border border-neutral-700' :
            mode === 'testnet' ? 'text-yellow-500 border border-yellow-700' :
            'text-red-400 border border-red-700'
          }`}>{modeLabel}</span>
          <div className="w-px h-3 bg-neutral-800" />
        </>
      )}

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <span className="text-[10px] text-neutral-600 uppercase">Bank</span>
        <span className="text-sm font-semibold tabular-nums text-neutral-100">
          ${bankroll >= 1000 ? (bankroll / 1000).toFixed(1) + 'K' : bankroll.toFixed(0)}
        </span>
      </motion.div>

      <div className="w-px h-3 bg-neutral-800" />

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.05 }}>
        <span className="text-[10px] text-neutral-600 uppercase">Equity</span>
        {equityCurve.length > 1 && (
          <ResponsiveContainer width={40} height={20}>
            <LineChart data={equityCurve}>
              <Line type="monotone" dataKey="bankroll" stroke={pnl >= 0 ? '#22c55e' : '#ef4444'} dot={false} strokeWidth={1} />
            </LineChart>
          </ResponsiveContainer>
        )}
        <span className="text-sm font-semibold tabular-nums text-neutral-100">
          ${totalEquity >= 1000 ? (totalEquity / 1000).toFixed(1) + 'K' : totalEquity.toFixed(0)}
        </span>
      </motion.div>

      <div className="w-px h-3 bg-neutral-800" />

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
        <span className="text-[10px] text-neutral-600 uppercase">P&L</span>
        <span className={`text-sm font-semibold tabular-nums ${pnl >= 0 ? 'text-green-500 glow-green' : 'text-red-500 glow-red'}`}>
          {pnl >= 0 ? '+' : '-'}${Math.abs(pnl).toFixed(0)}
        </span>
        <span className={`text-[10px] tabular-nums ${returnPercent >= 0 ? 'text-green-500/60' : 'text-red-500/60'}`}>
          {returnPercent >= 0 ? '+' : ''}{returnPercent.toFixed(1)}%
        </span>
      </motion.div>

      <div className="w-px h-3 bg-neutral-800" />

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}>
        <span className="text-[10px] text-neutral-600 uppercase">Win</span>
        <span className={`text-sm font-semibold tabular-nums ${winRate >= 55 ? 'text-green-500' : winRate >= 45 ? 'text-yellow-500' : 'text-red-500'}`}>
          {winRate.toFixed(0)}%
        </span>
        <span className="text-[10px] text-neutral-600 tabular-nums">
          {wins}/{trades}
        </span>
      </motion.div>

      <div className="w-px h-3 bg-neutral-800" />

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
        <span className="text-[10px] text-neutral-600 uppercase">Settled</span>
        <span className="text-sm font-semibold tabular-nums text-neutral-100">{trades}</span>
        {isRunning && <div className="live-dot" />}
      </motion.div>

      <div className="w-px h-3 bg-neutral-800" />

      <motion.div className="flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }}>
        <span className="text-[10px] text-neutral-600 uppercase">Open</span>
        <span className="text-sm font-semibold tabular-nums text-amber-400">{openTrades}</span>
        <span className="text-[10px] text-neutral-600 tabular-nums">${openExposure.toFixed(0)} locked</span>
      </motion.div>
    </div>
  )
}
