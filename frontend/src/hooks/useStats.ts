import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { BotStats } from '../types'

export function useStats() {
  const [wsStats, setWsStats] = useState<BotStats | null>(null)

  useEffect(() => {
    const apiKey = localStorage.getItem('adminApiKey') || ''
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/dashboard-data?token=${apiKey}`
    
    let ws: WebSocket | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {}
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'stats_update' && msg.data) {
            setWsStats(msg.data)
          }
        } catch (e) {
          console.error('Failed to parse stats WebSocket message:', e)
        }
      }
      
      ws.onerror = () => {}
      
      ws.onclose = () => {
        reconnectTimeout = setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) {
        ws.onclose = null
        ws.close()
      }
    }
  }, [])

  const { data: fallbackData, isLoading, error } = useQuery({
    queryKey: ['stats-unified'],
    queryFn: async () => {
      const { fetchDashboard } = await import('../api')
      const dashboard = await fetchDashboard()
      return dashboard.stats
    },
    refetchInterval: 10000,
  })

  const stats = wsStats || fallbackData || ({
    is_running: false,
    last_run: null,
    total_trades: 0,
    total_pnl: 0,
    bankroll: 10000,
    winning_trades: 0,
    win_rate: 0,
    initial_bankroll: 10000,
    mode: 'paper',
    paper: { pnl: 0, bankroll: 10000, trades: 0, wins: 0, win_rate: 0 },
    testnet: { pnl: 0, bankroll: 0, trades: 0, wins: 0, win_rate: 0 },
    live: { pnl: 0, bankroll: 0, trades: 0, wins: 0, win_rate: 0 },
  } as BotStats)

  // Use mode-specific stats when available (paper/testnet/live split)
  const active = stats.mode === 'live' && stats.live
    ? stats.live
    : stats.mode === 'testnet' && stats.testnet
      ? stats.testnet
      : stats.paper || null

  const settledPnl = active ? active.pnl : stats.total_pnl
  const wins = active ? active.wins : stats.winning_trades
  const trades = active ? active.trades : stats.total_trades
  const bankroll = active ? active.bankroll : stats.bankroll
  const initialBankroll = stats.initial_bankroll || 10000
  const totalPnl = settledPnl + (stats.unrealized_pnl ?? 0)

  return {
    stats,
    isLoading,
    error,

    pnl: totalPnl,
    settledPnl,
    wins,
    trades,
    bankroll,
    winRate: trades > 0 ? (wins / trades * 100) : 0,
    returnPercent: initialBankroll > 0 ? (totalPnl / initialBankroll * 100) : 0,
    isRunning: stats.is_running,
    lastRun: stats.last_run,
    mode: stats.mode,
    openExposure: stats.open_exposure ?? 0,
    openTrades: stats.open_trades ?? 0,
    settledTrades: stats.settled_trades ?? 0,
    settledWins: stats.settled_wins ?? 0,
    unrealizedPnl: stats.unrealized_pnl ?? 0,
    positionCost: stats.position_cost ?? 0,
    positionMarketValue: stats.position_market_value ?? 0,
    totalEquity: bankroll + (stats.position_market_value ?? 0),

    // Paper/Testnet/Live specific
    paperStats: stats.paper,
    testnetStats: stats.testnet,
    liveStats: stats.live,
  }
}
