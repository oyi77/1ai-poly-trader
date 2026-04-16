import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchStrategies, updateStrategy, runStrategyNow } from '../../api'

const MODES = [
  { value: '', label: 'Global', color: 'text-neutral-500' },
  { value: 'paper', label: 'Paper', color: 'text-green-500' },
  { value: 'testnet', label: 'Testnet', color: 'text-yellow-500' },
  { value: 'live', label: 'Live', color: 'text-red-500' },
]

export function StrategiesTab() {
  const qc = useQueryClient()
  const [runState, setRunState] = useState<Record<string, 'idle' | 'running' | 'done' | 'error'>>({})
  const [warnState, setWarnState] = useState<Record<string, string>>({})

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    refetchInterval: 30_000,
  })

  const handleToggle = async (name: string, enabled: boolean) => {
    const strat = strategies.find((s: any) => s.name === name)
    const requiredCreds = strat?.required_credentials || []

    if (enabled && requiredCreds.length > 0) {
      setWarnState(s => ({ ...s, [name]: `Enabled ${name} (needs: ${requiredCreds.join(', ')})` }))
      setTimeout(() => setWarnState(s => { const n = {...s}; delete n[name]; return n }), 5000)
    }

    await updateStrategy(name, { enabled: !enabled })
    qc.invalidateQueries({ queryKey: ['strategies'] })
  }

  const handleModeChange = async (name: string, mode: string) => {
    await updateStrategy(name, { trading_mode: mode || null })
    qc.invalidateQueries({ queryKey: ['strategies'] })
  }

  const handleRunNow = async (name: string) => {
    setRunState(s => ({ ...s, [name]: 'running' }))
    try {
      await runStrategyNow(name)
      setRunState(s => ({ ...s, [name]: 'done' }))
      setTimeout(() => setRunState(s => ({ ...s, [name]: 'idle' })), 2000)
    } catch (e: any) {
      setRunState(s => ({ ...s, [name]: 'error' }))
      setWarnState(s => ({ ...s, [name]: e?.message || 'Run failed' }))
      setTimeout(() => {
        setRunState(s => ({ ...s, [name]: 'idle' }))
        setWarnState(s => { const n = {...s}; delete n[name]; return n })
      }, 3000)
    }
  }

  if (isLoading) return <div className="text-[10px] text-neutral-600">Loading strategies...</div>

  return (
    <div className="space-y-2">
      <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">
        Strategies — {strategies.length} total
      </div>
      {strategies.map((s: any) => {
        const currentMode = MODES.find(m => m.value === (s.trading_mode || '')) || MODES[0]
        return (
          <div key={s.name} className="border border-neutral-800 p-3 space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-[11px] text-neutral-200 font-mono">{s.name}</span>
                <span className="text-[9px] text-neutral-600 uppercase tracking-wider">{s.category}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleRunNow(s.name)}
                  disabled={runState[s.name] === 'running'}
                  className={`px-2 py-0.5 border border-neutral-700 text-neutral-400 text-[9px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40 ${
                    runState[s.name] === 'done' ? 'border-green-700 text-green-500' :
                    runState[s.name] === 'error' ? 'border-red-700 text-red-500' : ''
                  }`}
                >
                  {runState[s.name] === 'running' ? 'Running...' : runState[s.name] === 'done' ? 'Done' : runState[s.name] === 'error' ? 'Error' : 'Run Now'}
                </button>
                <button
                  onClick={() => handleToggle(s.name, s.enabled)}
                  className={`px-2 py-0.5 border text-[9px] uppercase tracking-wider transition-colors ${
                    s.enabled
                      ? 'border-green-700 text-green-500 hover:border-red-700 hover:text-red-500'
                      : 'border-neutral-700 text-neutral-500 hover:border-green-700 hover:text-green-500'
                  }`}
                >
                  {s.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            </div>
            <div className="text-[10px] text-neutral-500">{s.description}</div>
            <div className="flex items-center gap-4">
              <div className="text-[9px] text-neutral-600 font-mono">interval: {s.interval_seconds}s</div>
              <div className="flex items-center gap-1">
                <span className="text-[9px] text-neutral-600 font-mono">mode:</span>
                <select
                  value={s.trading_mode || ''}
                  onChange={(e) => handleModeChange(s.name, e.target.value)}
                  className={`bg-transparent border border-neutral-800 text-[9px] font-mono px-1 py-0.5 focus:border-neutral-600 focus:outline-none cursor-pointer ${currentMode.color}`}
                >
                  {MODES.map(m => (
                    <option key={m.value} value={m.value} className="bg-neutral-900 text-neutral-300">
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {s.required_credentials && s.required_credentials.length > 0 && (
              <div className="text-[9px] text-amber-600/80 font-mono">
                Requires: {s.required_credentials.join(', ')}
              </div>
            )}
            {warnState[s.name] && (
              <div className={`text-[9px] font-mono mt-1 ${runState[s.name] === 'error' ? 'text-red-500' : 'text-amber-500'}`}>
                {warnState[s.name]}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
