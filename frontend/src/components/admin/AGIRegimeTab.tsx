import { useQuery } from '@tanstack/react-query'
import { agiAPI } from '../../api/agi'

const REGIME_ICONS: Record<string, string> = {
  bull: '▲', bear: '▼', sideways: '↔', sideways_volatile: '↯', crisis: '⚠', unknown: '?',
}

const REGIME_COLORS: Record<string, string> = {
  bull: 'text-green-400', bear: 'text-red-400', sideways: 'text-amber-400',
  sideways_volatile: 'text-orange-400', crisis: 'text-red-600', unknown: 'text-neutral-500',
}

const GOAL_LABELS: Record<string, string> = {
  maximize_pnl: 'Maximize P&L', preserve_capital: 'Preserve Capital',
  grow_allocation: 'Grow Allocation', reduce_exposure: 'Reduce Exposure',
}

export function AGIRegimeTab() {
  const { data: regimeData, isLoading: regimeLoading } = useQuery({
    queryKey: ['agi', 'regime'],
    queryFn: () => agiAPI.getRegime(),
    refetchInterval: 30_000,
  })

  const { data: goalData, isLoading: goalLoading } = useQuery({
    queryKey: ['agi', 'goal'],
    queryFn: () => agiAPI.getGoal(),
    refetchInterval: 30_000,
  })

  if (regimeLoading || goalLoading) {
    return <div className="text-[10px] text-neutral-600">Loading regime data...</div>
  }

  const regime = (regimeData?.regime || 'unknown').toLowerCase()
  const confidence = regimeData?.confidence ?? 0
  const history = regimeData?.history || []
  const goal = (goalData?.goal || 'unknown').toLowerCase()
  const goalPerformance = goalData?.performance

  return (
    <div className="space-y-4">
      {/* Current Regime */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Market Regime Detection</div>
        <div className="flex items-center gap-4 mb-4">
          <div className={`text-4xl font-mono ${REGIME_COLORS[regime]}`}>
            {REGIME_ICONS[regime]}
          </div>
          <div>
            <div className={`text-xl font-mono font-bold ${REGIME_COLORS[regime]}`}>
              {regime.toUpperCase().replace('_', ' ')}
            </div>
            <div className="text-[10px] text-neutral-500">
              Confidence: <span className="text-neutral-300 tabular-nums">{(confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <div className="h-1.5 bg-neutral-800 w-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                confidence >= 0.7 ? 'bg-green-500' : confidence >= 0.4 ? 'bg-amber-500' : 'bg-red-500'
              }`}
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-[8px] text-neutral-600 uppercase tracking-tighter">
            <span>Low Confidence</span>
            <span>Medium</span>
            <span>High Confidence</span>
          </div>
        </div>
      </div>

      {/* Goal Status */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Active Objective</div>
        <div className="flex items-start gap-3">
          <div className="text-xl">🎯</div>
          <div className="space-y-1">
            <div className="text-[12px] font-mono font-bold text-blue-400">
              {GOAL_LABELS[goal] || goal.toUpperCase().replace('_', ' ')}
            </div>
            {goalData?.reason && (
              <div className="text-[10px] text-neutral-500 leading-tight">{goalData.reason}</div>
            )}
            {goalData?.set_at && (
              <div className="text-[9px] text-neutral-600 italic">
                Activated: {new Date(goalData.set_at).toLocaleString()}
              </div>
            )}
          </div>
        </div>

        {goalPerformance && (
          <div className="mt-4 grid grid-cols-3 gap-2">
            <div className="border border-neutral-800 p-2">
              <div className="text-[8px] text-neutral-600 uppercase">Metric</div>
              <div className="text-[10px] text-neutral-300 font-mono">{goalPerformance.metric}</div>
            </div>
            <div className="border border-neutral-800 p-2">
              <div className="text-[8px] text-neutral-600 uppercase">Current</div>
              <div className="text-[10px] text-neutral-300 font-mono tabular-nums">{goalPerformance.value.toFixed(3)}</div>
            </div>
            <div className="border border-neutral-800 p-2">
              <div className="text-[8px] text-neutral-600 uppercase">Target</div>
              <div className="text-[10px] text-neutral-300 font-mono tabular-nums">{goalPerformance.target.toFixed(3)}</div>
            </div>
          </div>
        )}
      </div>

      {/* History Timeline */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Regime History</div>
        {history.length === 0 ? (
          <div className="text-[10px] text-neutral-700">No history available</div>
        ) : (
          <div className="space-y-1.5">
            {history.slice().reverse().slice(0, 10).map((entry, idx) => (
              <div key={idx} className="flex items-center gap-3 text-[10px] font-mono border-b border-neutral-800/40 pb-1 last:border-0">
                <span className={`w-4 text-center ${REGIME_COLORS[entry.regime.toLowerCase()] || 'text-neutral-500'}`}>
                  {REGIME_ICONS[entry.regime.toLowerCase()] || '?'}
                </span>
                <span className={`flex-1 ${REGIME_COLORS[entry.regime.toLowerCase()] || 'text-neutral-500'} uppercase`}>
                  {entry.regime.replace('_', ' ')}
                </span>
                <span className="text-neutral-600 tabular-nums">{(entry.confidence * 100).toFixed(0)}%</span>
                <span className="text-neutral-700 text-[9px]">
                  {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
