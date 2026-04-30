import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { agiAPI, type DecisionEntry } from '../../api/agi'

const DECISION_TYPE_COLOR: Record<string, string> = {
  agi_cycle: 'text-blue-400',
  agi_emergency_stop: 'text-red-400',
  goal_set: 'text-amber-400',
  regime_change: 'text-purple-400',
  allocation: 'text-green-400',
}

export function AGIDecisionsTab() {
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15

  const { data, isLoading } = useQuery({
    queryKey: ['agi', 'decisions', page],
    queryFn: () => agiAPI.getDecisions(page, PAGE_SIZE),
    refetchInterval: 30_000,
  })

  const log = data ?? { decisions: [], page: 1, total: 0, page_size: PAGE_SIZE }
  const totalPages = Math.max(1, Math.ceil(log.total / log.page_size))

  return (
    <div className="space-y-4">
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider">Decision Audit Log</div>
          <div className="text-[9px] text-neutral-600 tabular-nums">{log.total} total entries</div>
        </div>

        {isLoading ? (
          <div className="text-[10px] text-neutral-600">Loading...</div>
        ) : log.decisions.length === 0 ? (
          <div className="text-[10px] text-neutral-700 py-4 text-center">No decisions recorded yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] font-mono min-w-[600px]">
              <thead>
                <tr className="border-b border-neutral-800">
                  <th className="text-left px-2 py-1.5 text-neutral-600 font-normal whitespace-nowrap">Timestamp</th>
                  <th className="text-left px-2 py-1.5 text-neutral-600 font-normal whitespace-nowrap">Agent</th>
                  <th className="text-left px-2 py-1.5 text-neutral-600 font-normal whitespace-nowrap">Type</th>
                  <th className="text-left px-2 py-1.5 text-neutral-600 font-normal">Reasoning</th>
                  <th className="text-right px-2 py-1.5 text-neutral-600 font-normal whitespace-nowrap">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {log.decisions.map((entry: DecisionEntry, i: number) => (
                  <tr key={i} className="border-b border-neutral-800/40 hover:bg-neutral-800/20 transition-colors">
                    <td className="px-2 py-1.5 text-neutral-600 whitespace-nowrap tabular-nums">
                      {new Date(entry.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                    </td>
                    <td className="px-2 py-1.5 text-neutral-400 whitespace-nowrap">{entry.agent_name ?? '—'}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      <span className={`${DECISION_TYPE_COLOR[entry.decision_type] ?? 'text-neutral-400'}`}>
                        {entry.decision_type}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-neutral-500 max-w-xs truncate" title={entry.reasoning}>
                      {entry.reasoning ?? '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-neutral-500">
                      {entry.confidence != null ? `${(entry.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-neutral-800">
          <button
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
            className="px-2 py-1 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[9px] uppercase hover:border-neutral-600 transition-colors disabled:opacity-30"
          >
            ← Prev
          </button>
          <span className="text-[9px] text-neutral-600 tabular-nums">
            Page {log.page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(p => p + 1)}
            className="px-2 py-1 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[9px] uppercase hover:border-neutral-600 transition-colors disabled:opacity-30"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  )
}
