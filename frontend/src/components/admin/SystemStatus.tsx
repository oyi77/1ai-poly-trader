import { POLL } from '../../polling'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSystemStatus, startBot, stopBot, toggleTradingMode, resetBot } from '../../api'

const MODE_BADGES: Record<string, { label: string; className: string }> = {
  paper: { label: 'Paper', className: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  testnet: { label: 'Testnet', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
  live: { label: 'Live', className: 'bg-red-500/10 text-red-400 border-red-500/20' },
}

const MODES = [
  { key: 'paper', label: 'Paper', desc: 'Simulated trades, real market data', credKey: 'creds_paper' as const, missingKey: null },
  { key: 'testnet', label: 'Testnet', desc: 'Real orders on Amoy testnet', credKey: 'creds_testnet' as const, missingKey: 'missing_for_testnet' as const },
  { key: 'live', label: 'Live', desc: 'Real money on Polygon mainnet', credKey: 'creds_live' as const, missingKey: 'missing_for_live' as const },
] as const

export function SystemStatus() {
  const queryClient = useQueryClient()
  const [modeError, setModeError] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-system'],
    queryFn: fetchSystemStatus,
    refetchInterval: POLL.NORMAL,
  })

  const startMutation = useMutation({
    mutationFn: startBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-system'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-system'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const modeMutation = useMutation({
    mutationFn: ({ mode, active }: { mode: 'paper' | 'testnet' | 'live'; active: boolean }) =>
      toggleTradingMode(mode, active),
    onSuccess: () => {
      setModeError(null)
      queryClient.invalidateQueries({ queryKey: ['admin-system'] })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      setModeError(detail || err?.message || 'Failed to toggle mode')
    },
  })

  const resetMutation = useMutation({
    mutationFn: resetBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-system'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['stats-unified'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider">Loading system status...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[10px] text-red-500 uppercase tracking-wider">Failed to load system status</div>
      </div>
    )
  }

  const activeModes = new Set(data.active_modes ?? [data.trading_mode])

  return (
    <div className="space-y-4">
      {/* Mode Toggles */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Trading Modes</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {MODES.map(m => {
            const ready = data[m.credKey]
            const missing = m.missingKey ? data[m.missingKey] : []
            const active = activeModes.has(m.key)
            const isOnlyActive = active && activeModes.size <= 1
            return (
              <button
                key={m.key}
                disabled={modeMutation.isPending || (isOnlyActive && active)}
                onClick={() => modeMutation.mutate({ mode: m.key as 'paper' | 'testnet' | 'live', active: !active })}
                title={missing.length > 0 && !active ? `Missing: ${missing.join(', ')}` : m.desc}
                className={`relative p-2.5 border text-left transition-colors disabled:cursor-not-allowed ${
                  active
                    ? `${MODE_BADGES[m.key].className} border-current`
                    : 'border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-300'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider">{m.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${ready ? 'bg-green-500' : 'bg-red-500/60'}`} />
                    <div className={`w-3.5 h-2 rounded-sm border transition-colors ${
                      active ? 'bg-current border-current' : 'border-neutral-600'
                    }`} />
                  </div>
                </div>
                <div className="text-[9px] text-neutral-600 leading-tight">{m.desc}</div>
                {!ready && missing.length > 0 && (
                  <div className="text-[8px] text-red-500/70 mt-1 truncate">
                    Need: {missing.map(k => k.replace('POLYMARKET_', '')).join(', ')}
                  </div>
                )}
                {active && (
                  <div className="absolute top-1 right-1 w-1 h-1 rounded-full bg-current opacity-60" />
                )}
              </button>
            )
          })}
        </div>
        {modeError && (
          <div className="mt-2 text-[10px] text-red-400">{modeError}</div>
        )}
        {modeMutation.isPending && (
          <div className="mt-2 text-[10px] text-neutral-500">Toggling mode...</div>
        )}
      </div>

      {/* Bot Status */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="border border-neutral-800 bg-neutral-900/20 p-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Active Modes</div>
          <div className="flex gap-1.5 flex-wrap">
            {[...activeModes].map(mode => {
              const badge = MODE_BADGES[mode] || MODE_BADGES.paper
              return (
                <span key={mode} className={`px-2 py-0.5 text-[10px] font-bold uppercase border ${badge.className}`}>
                  {badge.label}
                </span>
              )
            })}
          </div>
        </div>
        <div className="border border-neutral-800 bg-neutral-900/20 p-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Bot Status</div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${data.bot_running ? 'bg-green-500' : 'bg-neutral-600'}`} />
            <span className={`text-xs font-bold uppercase ${data.bot_running ? 'text-green-500' : 'text-neutral-500'}`}>
              {data.bot_running ? 'Running' : 'Stopped'}
            </span>
            <button
              onClick={() => data.bot_running ? stopMutation.mutate() : startMutation.mutate()}
              disabled={startMutation.isPending || stopMutation.isPending}
              className={`ml-auto px-2.5 py-1 text-[10px] uppercase tracking-wider border transition-colors disabled:opacity-50 ${
                data.bot_running
                  ? 'bg-red-500/10 border-red-500/30 text-red-400 hover:bg-red-500/20'
                  : 'bg-green-500/10 border-green-500/30 text-green-400 hover:bg-green-500/20'
              }`}
            >
              {data.bot_running ? 'Stop' : 'Start'}
            </button>
            <button
              onClick={() => {
                if (confirm('Reset bot? This will delete all trades and reset bankroll to initial value.')) {
                  resetMutation.mutate()
                }
              }}
              disabled={resetMutation.isPending}
              className="ml-2 px-2.5 py-1 text-[10px] uppercase tracking-wider border border-orange-500/30 text-orange-400 bg-orange-500/10 hover:bg-orange-500/20 transition-colors disabled:opacity-50"
            >
              {resetMutation.isPending ? 'Resetting...' : 'Reset'}
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="border border-neutral-800 bg-neutral-900/20 p-3">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Pending Trades</div>
          <div className="text-lg font-bold text-neutral-200 tabular-nums">{data.pending_trades}</div>
        </div>
        <div className="border border-neutral-800 bg-neutral-900/20 p-3">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Total Trades</div>
          <div className="text-lg font-bold text-neutral-200 tabular-nums">{data.db_trade_count}</div>
        </div>
        <div className="border border-neutral-800 bg-neutral-900/20 p-3">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Total Signals</div>
          <div className="text-lg font-bold text-neutral-200 tabular-nums">{data.db_signal_count}</div>
        </div>
      </div>

      {/* Uptime */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-3">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Uptime</div>
        <div className="text-xs text-neutral-300 font-mono tabular-nums">
          {Math.floor(data.uptime_seconds / 3600)}h {Math.floor((data.uptime_seconds % 3600) / 60)}m {data.uptime_seconds % 60}s
        </div>
      </div>

      {/* Feature Flags */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Features</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { label: 'Telegram', enabled: data.telegram_configured },
            { label: 'Kalshi', enabled: data.kalshi_enabled },
            { label: 'Weather', enabled: data.weather_enabled },
          ].map(f => (
            <div key={f.label} className="flex items-center gap-2">
              <span className={`text-xs ${f.enabled ? 'text-green-500' : 'text-neutral-600'}`}>
                {f.enabled ? '[+]' : '[-]'}
              </span>
              <span className={`text-[10px] uppercase tracking-wider ${f.enabled ? 'text-neutral-300' : 'text-neutral-600'}`}>
                {f.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
