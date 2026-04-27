import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTradeAttempts, fetchTradeAttemptSummary } from '../../api'
import type { TradeAttempt } from '../../types'

const STATUSES = ['all', 'EXECUTED', 'REJECTED', 'BLOCKED', 'FAILED'] as const
const MODES = ['all', 'paper', 'testnet', 'live'] as const

function fmtMoney(value: number | null | undefined): string {
  if (value == null) return '—'
  return `$${value.toFixed(2)}`
}

function fmtPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(0)}%`
}

function statusClass(status: string): string {
  if (status === 'EXECUTED') return 'text-green-400 border-green-500/30 bg-green-500/10'
  if (status === 'REJECTED') return 'text-red-400 border-red-500/30 bg-red-500/10'
  if (status === 'BLOCKED') return 'text-amber-400 border-amber-500/30 bg-amber-500/10'
  if (status === 'FAILED') return 'text-purple-300 border-purple-500/30 bg-purple-500/10'
  return 'text-neutral-400 border-neutral-700 bg-neutral-900'
}

function AttemptRow({ attempt }: { attempt: TradeAttempt }) {
  const [expanded, setExpanded] = useState(false)
  const factors = typeof attempt.factors === 'object' && attempt.factors !== null ? attempt.factors : null
  const signalData = typeof attempt.signal_data === 'object' && attempt.signal_data !== null ? attempt.signal_data : null
  const reasoning = typeof signalData?.reasoning === 'string' ? signalData.reasoning : null

  return (
    <div className="border-b border-neutral-800/60 hover:bg-neutral-900/30 transition-colors">
      <button type="button" onClick={() => setExpanded(v => !v)} className="w-full grid grid-cols-[110px_90px_120px_minmax(180px,1fr)_100px_90px_90px] gap-3 px-3 py-2 text-left text-[10px] font-mono items-center">
        <span className="text-neutral-600 whitespace-nowrap">{attempt.created_at ? new Date(attempt.created_at).toLocaleTimeString('en-US', { hour12: false }) : '—'}</span>
        <span className={`px-1.5 py-0.5 border text-[9px] uppercase tracking-wider text-center ${statusClass(attempt.status)}`}>{attempt.status}</span>
        <span className="text-neutral-500 truncate" title={attempt.strategy}>{attempt.strategy}</span>
        <span className="text-neutral-300 truncate" title={attempt.market_ticker}>{attempt.market_ticker}</span>
        <span className="text-neutral-500 uppercase">{attempt.mode}</span>
        <span className="text-right text-neutral-400 tabular-nums">{fmtMoney(attempt.adjusted_size ?? attempt.requested_size)}</span>
        <span className="text-right text-neutral-400 tabular-nums">{fmtPct(attempt.confidence)}</span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 grid grid-cols-1 xl:grid-cols-3 gap-3 text-[10px] font-mono">
          <div className="bg-neutral-950 border border-neutral-800 p-3">
            <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-2">Why</div>
            <div className="text-neutral-300 mb-1">{attempt.reason ?? 'No reason recorded'}</div>
            <div className="text-neutral-600 break-all">{attempt.reason_code}</div>
            {attempt.risk_reason && <div className="mt-2 text-amber-300/80">Risk: {attempt.risk_reason}</div>}
          </div>
          <div className="bg-neutral-950 border border-neutral-800 p-3">
            <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-2">Gate Factors</div>
            <div className="grid grid-cols-2 gap-y-1">
              <span className="text-neutral-600">Bankroll</span><span className="text-right text-neutral-300">{fmtMoney(attempt.bankroll ?? (typeof factors?.bankroll === 'number' ? factors.bankroll : undefined))}</span>
              <span className="text-neutral-600">Exposure</span><span className="text-right text-neutral-300">{fmtMoney(attempt.current_exposure ?? (typeof factors?.current_exposure === 'number' ? factors.current_exposure : undefined))}</span>
              <span className="text-neutral-600">Requested</span><span className="text-right text-neutral-300">{fmtMoney(attempt.requested_size)}</span>
              <span className="text-neutral-600">Entry</span><span className="text-right text-neutral-300">{attempt.entry_price?.toFixed(3) ?? '—'}</span>
              <span className="text-neutral-600">Latency</span><span className="text-right text-neutral-300">{attempt.latency_ms != null ? `${attempt.latency_ms.toFixed(1)}ms` : '—'}</span>
            </div>
          </div>
          <div className="bg-neutral-950 border border-neutral-800 p-3">
            <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-2">AI / Signal Context</div>
            <div className="text-neutral-400 line-clamp-4">{reasoning ?? 'No AI reasoning captured on this attempt.'}</div>
            <div className="mt-2 text-neutral-700 break-all">corr: {attempt.correlation_id}</div>
          </div>
        </div>
      )}
    </div>
  )
}

export function ControlRoomTab() {
  const [mode, setMode] = useState<typeof MODES[number]>('all')
  const [status, setStatus] = useState<typeof STATUSES[number]>('all')
  const params = { limit: 100, ...(mode !== 'all' ? { mode } : {}), ...(status !== 'all' ? { status } : {}) }

  const attempts = useQuery({
    queryKey: ['trade-attempts', params],
    queryFn: () => fetchTradeAttempts(params),
    refetchInterval: 10_000,
  })
  const summary = useQuery({
    queryKey: ['trade-attempt-summary', mode],
    queryFn: () => fetchTradeAttemptSummary(mode !== 'all' ? { mode } : undefined),
    refetchInterval: 10_000,
  })

  if (attempts.isLoading || summary.isLoading) return <div className="flex items-center justify-center h-full text-neutral-500 text-sm">Loading Control Room...</div>
  if (attempts.error || summary.error) return <div className="flex items-center justify-center h-full text-red-500/70 text-sm">Failed to load Trade Control Room</div>

  const rows = attempts.data?.items ?? []
  const summaryData = summary.data

  return (
    <div className="h-full min-h-0 flex flex-col bg-black">
      <div className="shrink-0 border-b border-neutral-800 bg-neutral-950 px-3 py-3">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <div>
            <div className="text-xs font-bold text-neutral-100 uppercase tracking-widest font-mono">Trade Control Room</div>
            <div className="text-[10px] text-neutral-600 mt-0.5">Explains why AI-driven trades executed, paused, or were rejected.</div>
          </div>
          <div className="flex-1" />
          <select value={mode} onChange={e => setMode(e.target.value as typeof MODES[number])} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:outline-none">
            {MODES.map(m => <option key={m} value={m}>{m.toUpperCase()}</option>)}
          </select>
          <select value={status} onChange={e => setStatus(e.target.value as typeof STATUSES[number])} className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:outline-none">
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
          <div className="border border-neutral-800 bg-black p-2"><div className="text-neutral-600 uppercase">Attempts</div><div className="text-lg text-neutral-100">{summaryData?.total ?? 0}</div></div>
          <div className="border border-neutral-800 bg-black p-2"><div className="text-neutral-600 uppercase">Executed</div><div className="text-lg text-green-400">{summaryData?.executed ?? 0}</div></div>
          <div className="border border-neutral-800 bg-black p-2"><div className="text-neutral-600 uppercase">Blocked</div><div className="text-lg text-red-400">{summaryData?.blocked ?? 0}</div></div>
          <div className="border border-neutral-800 bg-black p-2"><div className="text-neutral-600 uppercase">Execution Rate</div><div className="text-lg text-cyan-400">{summaryData ? `${(summaryData.execution_rate * 100).toFixed(1)}%` : '0.0%'}</div></div>
        </div>
        {summaryData?.top_blockers?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {summaryData.top_blockers.map(blocker => (
              <span key={blocker.reason_code} className="px-2 py-1 border border-red-500/20 bg-red-500/5 text-red-300 text-[9px] font-mono uppercase tracking-wider">
                {blocker.reason_code}: {blocker.count}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-[110px_90px_120px_minmax(180px,1fr)_100px_90px_90px] gap-3 px-3 py-1.5 text-[9px] uppercase tracking-wider text-neutral-600 border-b border-neutral-800 bg-neutral-950 font-mono">
        <span>Time</span><span>Status</span><span>Strategy</span><span>Market</span><span>Mode</span><span className="text-right">Size</span><span className="text-right">Conf</span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {rows.map(row => <AttemptRow key={row.id} attempt={row} />)}
        {rows.length === 0 && <div className="py-16 text-center text-neutral-700 text-sm">No trade attempts recorded yet.</div>}
      </div>
    </div>
  )
}
