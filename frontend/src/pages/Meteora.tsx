import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { meteoraAPI, type MeteoraCandidate } from '../api/meteora'

const SUB_LABELS: Array<{ key: 'trading' | 'lp' | 'fees' | 'liquidity'; label: string }> = [
  { key: 'trading', label: 'TRD' },
  { key: 'lp', label: 'LP' },
  { key: 'fees', label: 'FEE' },
  { key: 'liquidity', label: 'LIQ' },
]

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const pct = Math.max(0, Math.min(100, (value ?? 0) * 100))
  return (
    <div className="flex items-center gap-1" title={`${label}: ${pct.toFixed(0)}%`}>
      <span className="text-[8px] text-neutral-600 w-6">{label}</span>
      <div className="w-10 h-1 bg-neutral-800">
        <div className="h-full bg-green-500/60" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function Meteora() {
  const qc = useQueryClient()
  const [includeRejected, setIncludeRejected] = useState(false)
  const [timeframe, setTimeframe] = useState('30m')
  const [category, setCategory] = useState('trending')
  const [screenMsg, setScreenMsg] = useState<string | null>(null)
  const [activeCycle, setActiveCycle] = useState<string | null>(null)

  const candidates = useQuery({
    queryKey: ['meteora', 'candidates', includeRejected],
    queryFn: () => meteoraAPI.getCandidates(200, includeRejected),
  })

  const latestCycle = useQuery({
    queryKey: ['meteora', 'cycles', 'latest'],
    queryFn: () => meteoraAPI.getLatestCycle(),
  })

  const cycleDetail = useQuery({
    queryKey: ['meteora', 'cycle', activeCycle],
    queryFn: () => meteoraAPI.getCandidatesForCycle(activeCycle!),
    enabled: !!activeCycle,
  })

  const screenNow = useMutation({
    mutationFn: () => meteoraAPI.screen(timeframe, category, 100),
    onSuccess: (s) => {
      setScreenMsg(
        `Cycle ${s.cycle_id}: ${s.accepted} accepted / ${s.rejected} rejected of ${s.screened}`,
      )
      qc.invalidateQueries({ queryKey: ['meteora'] })
    },
    onError: (e: Error) => setScreenMsg(`Screen failed: ${e.message}`),
  })

  const rows: MeteoraCandidate[] = candidates.data ?? []

  return (
    <div data-testid="meteora-page" className="space-y-4 max-w-6xl mx-auto p-4">
      <header className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-lg font-bold text-neutral-200">Meteora DLMM Screener</h1>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <select
            aria-label="timeframe"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="bg-neutral-900 border border-neutral-700 px-2 py-1"
          >
            {['5m', '30m', '1h', '4h', '24h'].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <select
            aria-label="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="bg-neutral-900 border border-neutral-700 px-2 py-1"
          >
            {['trending', 'new', 'top'].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <button
            onClick={() => screenNow.mutate()}
            disabled={screenNow.isPending}
            className="px-3 py-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 uppercase tracking-wider"
          >
            {screenNow.isPending ? 'Scanning…' : 'Screen now'}
          </button>
        </div>
      </header>

      {screenMsg && (
        <div data-testid="screen-msg" className="text-[11px] font-mono text-green-400">
          {screenMsg}
        </div>
      )}

      {latestCycle.data && (
        <div className="text-[10px] text-neutral-500 font-mono">
          Latest cycle {latestCycle.data.cycle_id} — {latestCycle.data.accepted}/
          {latestCycle.data.screened} accepted
        </div>
      )}

      <label className="flex items-center gap-2 text-[10px] text-neutral-400 uppercase tracking-wider">
        <input
          type="checkbox"
          checked={includeRejected}
          onChange={(e) => setIncludeRejected(e.target.checked)}
        />
        Show rejected
      </label>

      {candidates.isLoading ? (
        <div className="text-[11px] text-neutral-500">Loading candidates…</div>
      ) : rows.length === 0 ? (
        <div data-testid="empty-state" className="text-[11px] text-neutral-600">
          No candidates yet — hit “Screen now”.
        </div>
      ) : (
        <table data-testid="candidates-table" className="w-full text-[10px] font-mono">
          <thead>
            <tr className="text-neutral-600 uppercase text-left border-b border-neutral-800">
              <th className="py-1.5 pr-2">Pool</th>
              <th className="py-1.5 pr-2">Score</th>
              <th className="py-1.5 pr-2">Subscores</th>
              <th className="py-1.5 pr-2">Status</th>
              <th className="py-1.5 pr-2">Seen</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={`${r.cycle_id}-${r.pool_address}`}
                className="border-b border-neutral-800/40 hover:bg-neutral-900/40"
              >
                <td className="py-1.5 pr-2 text-neutral-300">{r.name}</td>
                <td className="py-1.5 pr-2 tabular-nums text-green-400 font-bold">
                  {r.degen_score?.toFixed(1)}
                </td>
                <td className="py-1.5 pr-2">
                  <div className="flex gap-2">
                    {SUB_LABELS.map(({ key, label }) => (
                      <ScoreBar key={key} label={label} value={r.subscores?.[key]} />
                    ))}
                  </div>
                </td>
                <td className="py-1.5 pr-2">
                  {r.rejected ? (
                    <span
                      className="text-red-400"
                      title={r.reject_reason ?? ''}
                    >
                      ✗ {r.reject_reason}
                    </span>
                  ) : (
                    <span className="text-green-500">✓ ok</span>
                  )}
                </td>
                <td className="py-1.5 pr-2 text-neutral-600">
                  {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {latestCycle.data && (
        <button
          onClick={() => setActiveCycle(latestCycle.data!.cycle_id)}
          className="text-[10px] underline text-neutral-500 hover:text-green-500"
        >
          Inspect latest cycle rows
        </button>
      )}

      {activeCycle && (
        <div data-testid="cycle-drawer" className="border border-neutral-800 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-wider text-neutral-500">
              Cycle {activeCycle} — full row set
            </div>
            <button
              onClick={() => setActiveCycle(null)}
              className="text-[10px] text-neutral-500 hover:text-neutral-300"
            >
              close
            </button>
          </div>
          <div className="text-[10px] font-mono text-neutral-400">
            {cycleDetail.isLoading
              ? 'Loading…'
              : `${cycleDetail.data?.length ?? 0} rows`}
          </div>
        </div>
      )}
    </div>
  )
}
