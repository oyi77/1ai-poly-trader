import { useEffect, useState } from 'react'
import {
  fetchPendingApprovals,
  approvePendingTrade,
  rejectPendingTrade,
  type PendingApproval,
} from '../api'

export default function PendingApprovals() {
  const [items, setItems] = useState<PendingApproval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchPendingApprovals()
      setItems(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleApprove = async (id: number) => {
    setBusyId(id)
    try {
      await approvePendingTrade(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  const handleReject = async (id: number) => {
    setBusyId(id)
    try {
      await rejectPendingTrade(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="flex flex-col h-full bg-neutral-950 text-neutral-200">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-neutral-800">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-neutral-200 uppercase tracking-wider">Pending Approvals</h1>
            <p className="text-[10px] text-neutral-600 mt-0.5">
              Trades below auto-approve confidence threshold — queued for manual review
            </p>
          </div>
          <button
            onClick={load}
            className="text-[10px] px-3 py-1 border border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-300 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="shrink-0 px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-[10px] text-red-400">
          Error: {error}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="px-4 py-12 text-center text-neutral-700 text-[10px]">Loading...</div>
        ) : items.length === 0 ? (
          <div className="px-4 py-12 text-center text-neutral-700 text-[10px]">No pending approvals</div>
        ) : (
          <table className="w-full text-[10px] font-mono">
            <thead className="sticky top-0 bg-neutral-950">
              <tr className="border-b border-neutral-800">
                <th className="text-left px-3 py-2 text-neutral-600 uppercase tracking-wider">Market</th>
                <th className="text-left px-3 py-2 text-neutral-600 uppercase tracking-wider">Side</th>
                <th className="text-right px-3 py-2 text-neutral-600 uppercase tracking-wider">Size</th>
                <th className="text-right px-3 py-2 text-neutral-600 uppercase tracking-wider">Confidence</th>
                <th className="text-left px-3 py-2 text-neutral-600 uppercase tracking-wider">Created</th>
                <th className="text-center px-3 py-2 text-neutral-600 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-b border-neutral-800/40 hover:bg-neutral-900/30">
                  <td className="px-3 py-2 text-neutral-300 truncate max-w-[150px]" title={it.market_id}>
                    {it.market_id.length > 20 ? `${it.market_id.slice(0, 18)}...` : it.market_id}
                  </td>
                  <td className={`px-3 py-2 font-bold ${it.direction === 'up' || it.direction === 'yes' ? 'text-green-400' : 'text-red-400'}`}>
                    {it.direction?.toUpperCase() ?? '--'}
                  </td>
                  <td className="px-3 py-2 text-right text-neutral-300 tabular-nums">${it.size.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <span className={`${it.confidence >= 0.7 ? 'text-green-400' : it.confidence >= 0.5 ? 'text-amber-400' : 'text-red-400'}`}>
                      {(it.confidence * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-3 py-2 text-neutral-600 whitespace-nowrap">
                    {it.created_at ? new Date(it.created_at).toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '--'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        disabled={busyId === it.id}
                        onClick={() => handleApprove(it.id)}
                        className="text-[9px] px-2.5 py-1 bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {busyId === it.id ? '...' : 'Approve'}
                      </button>
                      <button
                        disabled={busyId === it.id}
                        onClick={() => handleReject(it.id)}
                        className="text-[9px] px-2.5 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {busyId === it.id ? '...' : 'Reject'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer summary */}
      {items.length > 0 && (
        <div className="shrink-0 px-4 py-2 border-t border-neutral-800 flex items-center gap-4">
          <span className="text-[10px] text-neutral-600">{items.length} pending</span>
          <span className="text-[10px] text-neutral-600">
            Total size: <span className="text-neutral-400 tabular-nums">${items.reduce((s, i) => s + i.size, 0).toFixed(2)}</span>
          </span>
          <span className="text-[10px] text-neutral-600">
            Avg confidence: <span className="text-neutral-400 tabular-nums">{(items.reduce((s, i) => s + i.confidence, 0) / items.length * 100).toFixed(1)}%</span>
          </span>
        </div>
      )}
    </div>
  )
}
