import { motion } from 'framer-motion'

interface SystemEfficiencyPanelProps {
  avgDecisionTime: number // in seconds
  signalsProcessed24h: number
  tradesExecuted24h: number
  processUptimeSeconds: number
}

export function SystemEfficiencyPanel({
  avgDecisionTime,
  signalsProcessed24h,
  tradesExecuted24h,
  processUptimeSeconds,
}: SystemEfficiencyPanelProps) {
  const formatDecisionTime = (seconds: number) => {
    if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`
    return `${seconds.toFixed(1)}s`
  }

  const formatDuration = (seconds: number) => {
    if (seconds < 0) return '—'
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h`
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Avg Decision Time</div>
        <div className="text-2xl font-bold text-cyan-400 tabular-nums">
          {avgDecisionTime < 0 ? '—' : formatDecisionTime(avgDecisionTime)}
        </div>
        <div className="text-[10px] text-neutral-600 mt-1">Per signal</div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Signals Processed</div>
        <div className="text-2xl font-bold text-neutral-200 tabular-nums">{signalsProcessed24h < 0 ? '—' : signalsProcessed24h}</div>
        <div className="text-[10px] text-neutral-600 mt-1">Last 24 hours</div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Trades Executed</div>
        <div className="text-2xl font-bold text-neutral-200 tabular-nums">{tradesExecuted24h}</div>
        <div className="text-[10px] text-neutral-600 mt-1">Last 24 hours</div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Process Uptime</div>
        <div className={`text-2xl font-bold tabular-nums ${processUptimeSeconds < 0 ? 'text-neutral-600' : 'text-green-500'}`}>
          {formatDuration(processUptimeSeconds)}
        </div>
        <div className="text-[10px] text-neutral-600 mt-1">Since last restart</div>
      </motion.div>
    </div>
  )
}
