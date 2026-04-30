import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agiAPI } from '../../api/agi'

export function AGIControlTab() {
  const qc = useQueryClient()
  const [stopConfirm, setStopConfirm] = useState(false)
  const [cycleMsg, setCycleMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const { data: status } = useQuery({
    queryKey: ['agi', 'status'],
    queryFn: () => agiAPI.getStatus(),
    refetchInterval: 15_000,
  })

  const { data: regime } = useQuery({
    queryKey: ['agi', 'regime'],
    queryFn: () => agiAPI.getRegime(),
    refetchInterval: 30_000,
  })

  const { data: goal } = useQuery({
    queryKey: ['agi', 'goal'],
    queryFn: () => agiAPI.getGoal(),
    refetchInterval: 30_000,
  })

  const runCycle = useMutation({
    mutationFn: () => agiAPI.runCycle(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['agi'] })
      const errs = data.errors?.length ? ` (${data.errors.length} warnings)` : ''
      setCycleMsg({ ok: !data.errors?.length, text: `Cycle complete — ${data.actions_taken} actions taken${errs}` })
      setTimeout(() => setCycleMsg(null), 5000)
    },
    onError: (e: any) => {
      setCycleMsg({ ok: false, text: e.message ?? 'Cycle failed' })
      setTimeout(() => setCycleMsg(null), 5000)
    },
  })

  const emergencyStop = useMutation({
    mutationFn: () => agiAPI.emergencyStop(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agi'] })
      setStopConfirm(false)
    },
  })

  const goalOverride = useMutation({
    mutationFn: (g: string) => agiAPI.overrideGoal(g, 'manual override via admin'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agi'] }),
  })

  const REGIME_COLOR: Record<string, string> = {
    bull: 'text-green-400', bear: 'text-red-400',
    sideways: 'text-amber-400', sideways_volatile: 'text-orange-400',
    crisis: 'text-red-600', unknown: 'text-neutral-500',
  }
  const REGIME_ICON: Record<string, string> = {
    bull: '▲', bear: '▼', sideways: '↔', sideways_volatile: '↯', crisis: '⚠', unknown: '?',
  }
  const HEALTH_COLOR: Record<string, string> = {
    healthy: 'text-green-400', stopped: 'text-red-400', degraded: 'text-amber-400',
  }

  const r = regime?.regime ?? status?.regime ?? 'unknown'
  const g = goal?.goal ?? status?.goal ?? 'unknown'
  const health = status?.health ?? 'unknown'
  const stopped = status?.emergency_stop ?? false

  return (
    <div className="space-y-4">
      {/* Status Header */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">AGI Status</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="border border-neutral-800 p-2">
            <div className="text-[8px] text-neutral-600 uppercase mb-1">Regime</div>
            <div className={`text-[12px] font-mono font-bold ${REGIME_COLOR[r] ?? 'text-neutral-500'}`}>
              {REGIME_ICON[r]} {r.toUpperCase().replace('_', ' ')}
            </div>
            {regime?.confidence != null && (
              <div className="text-[9px] text-neutral-600 mt-0.5 tabular-nums">
                {(regime.confidence * 100).toFixed(0)}% confidence
              </div>
            )}
          </div>
          <div className="border border-neutral-800 p-2">
            <div className="text-[8px] text-neutral-600 uppercase mb-1">Current Goal</div>
            <div className="text-[11px] text-blue-400 font-mono font-bold">
              {g.replace('_', ' ').toUpperCase()}
            </div>
            {goal?.reason && (
              <div className="text-[9px] text-neutral-600 mt-0.5 truncate" title={goal.reason}>{goal.reason}</div>
            )}
          </div>
          <div className="border border-neutral-800 p-2">
            <div className="text-[8px] text-neutral-600 uppercase mb-1">Health</div>
            <div className={`text-[11px] font-mono font-bold ${HEALTH_COLOR[health] ?? 'text-neutral-400'}`}>
              {health.toUpperCase()}
            </div>
          </div>
          <div className="border border-neutral-800 p-2">
            <div className="text-[8px] text-neutral-600 uppercase mb-1">Emergency Stop</div>
            <div className={`text-[11px] font-mono font-bold ${stopped ? 'text-red-500' : 'text-neutral-500'}`}>
              {stopped ? '⛔ ACTIVE' : '○ Inactive'}
            </div>
          </div>
        </div>
      </div>

      {/* Allocations */}
      {status?.allocations && Object.keys(status.allocations).length > 0 && (
        <div className="border border-neutral-800 bg-neutral-900/20 p-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Strategy Allocations</div>
          <div className="space-y-1.5">
            {Object.entries(status.allocations).map(([strat, amt]) => {
              const total = Object.values(status.allocations!).reduce((s, v) => s + v, 0)
              const pct = total > 0 ? (amt / total) * 100 : 0
              return (
                <div key={strat} className="flex items-center gap-2">
                  <div className="text-[10px] text-neutral-400 font-mono w-36 truncate shrink-0">{strat}</div>
                  <div className="flex-1 h-1.5 bg-neutral-800">
                    <div className="h-full bg-green-500/60" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="text-[10px] text-neutral-500 font-mono tabular-nums w-16 text-right">
                    ${amt.toFixed(0)}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Actions</div>
        <div className="flex flex-wrap gap-2 items-center">
          <button
            onClick={() => runCycle.mutate()}
            disabled={runCycle.isPending || stopped}
            className="px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 text-blue-400 text-[10px] uppercase tracking-wider hover:bg-blue-500/20 transition-colors disabled:opacity-40"
          >
            {runCycle.isPending ? 'Running...' : 'Run AGI Cycle'}
          </button>

          {!stopConfirm ? (
            <button
              onClick={() => setStopConfirm(true)}
              disabled={stopped}
              className="px-3 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] uppercase tracking-wider hover:bg-red-500/20 transition-colors disabled:opacity-40"
            >
              Emergency Stop
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-red-400">Confirm?</span>
              <button
                onClick={() => emergencyStop.mutate()}
                disabled={emergencyStop.isPending}
                className="px-2 py-1 bg-red-500/20 border border-red-500/50 text-red-300 text-[10px] uppercase hover:bg-red-500/30 transition-colors"
              >
                Yes, Stop
              </button>
              <button
                onClick={() => setStopConfirm(false)}
                className="px-2 py-1 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[10px] uppercase hover:border-neutral-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {cycleMsg && (
            <span className={`text-[10px] font-mono ${cycleMsg.ok ? 'text-green-400' : 'text-amber-400'}`}>
              {cycleMsg.text}
            </span>
          )}
        </div>
      </div>

      {/* Goal Override */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Goal Override</div>
        <div className="flex flex-wrap gap-2">
          {['maximize_pnl', 'preserve_capital', 'grow_allocation', 'reduce_exposure'].map(g => (
            <button
              key={g}
              onClick={() => goalOverride.mutate(g)}
              disabled={goalOverride.isPending}
              className={`px-2 py-1 text-[10px] uppercase tracking-wider border transition-colors ${
                goal?.goal === g
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-300'
                  : 'bg-neutral-800 border-neutral-700 text-neutral-400 hover:border-neutral-500'
              }`}
            >
              {g.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
