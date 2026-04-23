import { motion } from 'framer-motion'

interface SelfImprovementMetricsProps {
  proposalsGenerated: number
  proposalsApproved: number
  performanceGain: number
  lastEvolution: string | null
}

export function SelfImprovementMetrics({
  proposalsGenerated,
  proposalsApproved,
  performanceGain,
  lastEvolution,
}: SelfImprovementMetricsProps) {
  const approvalRate = proposalsGenerated > 0 ? (proposalsApproved / proposalsGenerated) * 100 : 0

  const formatLastEvolution = (timestamp: string | null) => {
    if (!timestamp) return 'Never'
    const elapsed = Date.now() - new Date(timestamp).getTime()
    const hours = Math.floor(elapsed / (1000 * 60 * 60))
    const minutes = Math.floor((elapsed % (1000 * 60 * 60)) / (1000 * 60))
    if (hours > 0) return `${hours}h ago`
    return `${minutes}m ago`
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Proposals Generated</div>
        <div className="text-2xl font-bold text-neutral-200 tabular-nums">{proposalsGenerated}</div>
        <div className="text-[10px] text-neutral-600 mt-1">
          {proposalsApproved} approved ({approvalRate.toFixed(0)}%)
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Performance Gain</div>
        <div className={`text-2xl font-bold tabular-nums ${performanceGain >= 0 ? 'text-green-500' : 'text-red-500'}`}>
          {performanceGain >= 0 ? '+' : ''}{performanceGain.toFixed(1)}%
        </div>
        <div className="text-[10px] text-neutral-600 mt-1">Since last evolution</div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="col-span-2 border border-neutral-800 bg-neutral-900/30 p-3"
      >
        <div className="text-[9px] text-neutral-500 uppercase tracking-wider mb-1">Last Evolution</div>
        <div className="text-lg font-semibold text-neutral-300 tabular-nums">
          {formatLastEvolution(lastEvolution)}
        </div>
      </motion.div>
    </div>
  )
}
