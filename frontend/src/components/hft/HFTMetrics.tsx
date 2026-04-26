import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'

interface HFTMetrics {
  signals_per_second: number
  avg_signal_latency_ms: number
  executor_latency_ms: number
  dispatcher_queue_size: number
  active_strategies: number
  arb_opportunities: number
  whale_activities: number
  orderbook_updates_per_sec: number
  ws_connected: boolean
}

interface HFTStrategyStatus {
  name: string
  enabled: boolean
  signals_generated: number
  last_signal_at: string | null
  pnl: number
  mode: string
}

export function HFTMetrics() {
  const [metrics, setMetrics] = useState<HFTMetrics | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['hft-metrics'],
    queryFn: async () => {
      const { data } = await api.get<HFTMetrics>('/hft/metrics')
      return data
    },
    refetchInterval: 2000,
    retry: 1,
  })

  useEffect(() => {
    if (data) setMetrics(data)
  }, [data])

  if (isLoading && !metrics) {
    return (
      <div className="flex items-center justify-center py-4">
        <div className="text-[10px] text-neutral-600 uppercase tracking-wider">Loading HFT Metrics...</div>
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="flex items-center justify-center py-4">
        <div className="text-[10px] text-neutral-600 uppercase tracking-wider">No HFT data available</div>
      </div>
    )
  }

  const statItems = [
    { label: 'Signals/s', value: metrics.signals_per_second.toFixed(1), warn: metrics.signals_per_second < 1, ok: true },
    { label: 'Signal Latency', value: `${metrics.avg_signal_latency_ms.toFixed(0)}ms`, warn: metrics.avg_signal_latency_ms > 100, ok: metrics.avg_signal_latency_ms < 100 },
    { label: 'Executor', value: `${metrics.executor_latency_ms.toFixed(0)}ms`, warn: metrics.executor_latency_ms > 50, ok: metrics.executor_latency_ms < 50 },
    { label: 'Queue', value: metrics.dispatcher_queue_size.toString(), warn: metrics.dispatcher_queue_size > 100, ok: metrics.dispatcher_queue_size < 100 },
    { label: 'Active Strats', value: metrics.active_strategies.toString(), warn: false, ok: true },
    { label: 'Arb Opps', value: metrics.arb_opportunities.toString(), warn: false, ok: true },
    { label: 'Whales', value: metrics.whale_activities.toString(), warn: false, ok: true },
    { label: 'OB Updates/s', value: metrics.orderbook_updates_per_sec.toFixed(0), warn: false, ok: true },
  ]

  return (
    <div className="grid grid-cols-4 sm:grid-cols-8 gap-px bg-neutral-800 border border-neutral-800">
      {statItems.map((item, i) => (
        <motion.div
          key={item.label}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.05 }}
          className="bg-black px-2 py-1.5 flex flex-col items-center gap-0.5"
        >
          <span className="text-[9px] text-neutral-600 uppercase tracking-wider">{item.label}</span>
          <span className={`text-sm font-semibold tabular-nums ${
            item.warn ? 'text-yellow-500' : item.ok ? 'text-green-500' : 'text-neutral-400'
          }`}>
            {item.value}
          </span>
        </motion.div>
      ))}
      <div className="bg-black px-2 py-1.5 flex flex-col items-center gap-0.5">
        <span className="text-[9px] text-neutral-600 uppercase tracking-wider">WS</span>
        <div className="flex items-center gap-1">
          <span className={`inline-block w-2 h-2 rounded-full ${
            metrics.ws_connected ? 'bg-green-500' : 'bg-red-500'
          }`} />
          <span className={`text-sm font-semibold ${
            metrics.ws_connected ? 'text-green-500' : 'text-red-500'
          }`}>
            {metrics.ws_connected ? 'ON' : 'OFF'}
          </span>
        </div>
      </div>
    </div>
  )
}

export function HFTStrategyCards() {
  const { data, isLoading } = useQuery({
    queryKey: ['hft-strategies'],
    queryFn: async () => {
      const { data } = await api.get<{ strategies: HFTStrategyStatus[] }>('/hft/strategies')
      return data.strategies
    },
    refetchInterval: 5000,
    retry: 1,
  })

  if (isLoading) {
    return <div className="text-[10px] text-neutral-600">Loading strategies...</div>
  }

  const strategies = data ?? []

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {strategies.map((s) => (
        <div
          key={s.name}
          className={`border px-2 py-1.5 ${
            s.enabled
              ? s.pnl >= 0
                ? 'border-green-500/30 bg-green-500/5'
                : 'border-red-500/30 bg-red-500/5'
              : 'border-neutral-800 bg-neutral-900'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-neutral-300 uppercase truncate">
              {s.name.replace('_', ' ')}
            </span>
            <span className={`text-[8px] font-bold px-1 py-0.5 ${
              s.enabled ? 'bg-green-500/20 text-green-500' : 'bg-neutral-800 text-neutral-600'
            }`}>
              {s.enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[9px] text-neutral-600">{s.signals_generated} sigs</span>
            <span className={`text-[9px] font-semibold tabular-nums ${
              s.pnl >= 0 ? 'text-green-500' : 'text-red-500'
            }`}>
              {s.pnl >= 0 ? '+' : ''}{s.pnl.toFixed(2)}
            </span>
          </div>
        </div>
      ))}
      {strategies.length === 0 && (
        <div className="col-span-full text-center py-4 text-[10px] text-neutral-600">
          No HFT strategies active
        </div>
      )}
    </div>
  )
}