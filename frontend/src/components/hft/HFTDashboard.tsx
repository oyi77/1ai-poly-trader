import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../../api'
import { HFTMetrics, HFTStrategyCards } from './HFTMetrics'
import { HFTSignals } from './HFTSignals'

export default function HFTDashboard() {
  const queryClient = useQueryClient()

  const { data: strategies = [] } = useQuery({
    queryKey: ['hft-strategies'],
    queryFn: async () => {
      const { data } = await adminApi.get<{ strategies: Array<{ name: string; enabled: boolean }> }>('/hft/strategies')
      return data.strategies
    },
    retry: 1,
  })

  const toggleMutation = useMutation({
    mutationFn: async ({ name, enabled }: { name: string; enabled: boolean }) => {
      await adminApi.post('/hft/strategies/toggle', { name, enabled })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hft-strategies'] })
    },
  })

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider font-semibold">HFT Strategies</span>
        <div className="flex flex-wrap gap-1.5">
          {strategies.map((s) => (
            <button
              key={s.name}
              onClick={() => toggleMutation.mutate({ name: s.name, enabled: !s.enabled })}
              disabled={toggleMutation.isPending}
              className={`px-2 py-0.5 text-[9px] font-semibold uppercase border transition-colors ${
                s.enabled
                  ? 'bg-green-500/10 text-green-400 border-green-500/30 hover:bg-green-500/20'
                  : 'bg-neutral-800 text-neutral-500 border-neutral-700 hover:bg-neutral-700'
              }`}
            >
              {s.name.replace('_', ' ')}
            </button>
          ))}
          {strategies.length === 0 && (
            <>
              {['universal_scanner', 'probability_arb', 'cross_market_arb', 'whale_frontrun'].map((name) => (
                <button
                  key={name}
                  onClick={() => toggleMutation.mutate({ name, enabled: true })}
                  disabled={toggleMutation.isPending}
                  className="px-2 py-0.5 text-[9px] font-semibold uppercase border bg-neutral-800 text-neutral-500 border-neutral-700 hover:bg-neutral-700"
                >
                  {name.replace('_', ' ')}
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      <HFTMetrics />

      <HFTStrategyCards />

      <div className="border border-neutral-800">
        <div className="flex items-center justify-between px-2 py-1 border-b border-neutral-800">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider font-semibold">Live HFT Signals</span>
          <div className="flex items-center gap-1.5">
            <div className="live-dot" />
            <span className="text-[9px] text-green-500 uppercase tracking-wider">Live</span>
          </div>
        </div>
        <HFTSignals maxRows={8} />
      </div>
    </div>
  )
}