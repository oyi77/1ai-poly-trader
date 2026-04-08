import { useQuery } from '@tanstack/react-query'
import { fetchDashboard } from '../api'
import type { BotStats } from '../types'

/**
 * Single source of truth for all dashboard stats.
 * Ensures consistent values across all tabs and sections.
 */
export function useStats() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stats-unified'],
    queryFn: async () => {
      const dashboard = await fetchDashboard()
      return dashboard.stats
    },
    refetchInterval: 10000,
  })

  const stats = data || ({
    is_running: false,
    last_run: null,
    total_trades: 0,
    total_pnl: 0,
    bankroll: 10000,
    winning_trades: 0,
    win_rate: 0,
    mode: 'paper',
    paper: { pnl: 0, bankroll: 10000, trades: 0, wins: 0, win_rate: 0 },
    live: { pnl: 0, bankroll: 0, trades: 0, wins: 0, win_rate: 0 },
  } as BotStats)

  // Use mode-specific stats when available (paper/live split)
  const active = stats.mode === 'live' && stats.live
    ? stats.live
    : stats.paper || null

  // Derived values (computed once, used everywhere)
  const pnl = active ? active.pnl : stats.total_pnl
  const wins = active ? active.wins : stats.winning_trades
  const trades = active ? active.trades : stats.total_trades
  // Use mode-specific bankroll when available, otherwise use default
  const bankroll = active ? active.bankroll : stats.bankroll
  const winRate = trades > 0 ? (wins / trades) : 0
  const costBasis = bankroll - pnl
  const returnPercent = costBasis > 0 ? (pnl / costBasis * 100) : 0

  return {
    // Raw stats
    stats,
    isLoading,
    error,

    // Computed values (use these, not raw stats)
    pnl,
    wins,
    trades,
    bankroll,
    winRate,
    returnPercent,
    isRunning: stats.is_running,
    lastRun: stats.last_run,
    mode: stats.mode,

    // Paper/Live specific
    paperStats: stats.paper,
    liveStats: stats.live,
  }
}
