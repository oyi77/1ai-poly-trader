import { useEffect, useState } from 'react'
import {
  fetchPendingApprovals,
  approvePendingTrade,
  rejectPendingTrade,
  batchApprovePendingTrades,
  batchRejectPendingTrades,
  clearAllPendingTrades,
  type PendingApproval,
} from '../api'

export default function PendingApprovals() {
  const [items, setItems] = useState<PendingApproval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [batchBusy, setBatchBusy] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchPendingApprovals()
      setItems(data)
      setError(null)
      setSelectedIds(new Set())
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

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    setSelectedIds(next)
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((it) => it.id)))
    }
  }

  const handleBatchApprove = async () => {
    if (selectedIds.size === 0) return
    setBatchBusy(true)
    try {
      await batchApprovePendingTrades(Array.from(selectedIds))
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchBusy(false)
    }
  }

  const handleBatchReject = async () => {
    if (selectedIds.size === 0) return
    setBatchBusy(true)
    try {
      await batchRejectPendingTrades(Array.from(selectedIds))
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchBusy(false)
    }
  }

  const handleClearAll = async () => {
    if (items.length === 0) return
    setBatchBusy(true)
    try {
      await clearAllPendingTrades()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchBusy(false)
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

      {/* Batch Actions Bar */}
      {items.length > 0 && (
        <div className="shrink-0 px-4 py-2 bg-neutral-900/50 border-b border-neutral-800 flex items-center gap-2 flex-wrap">
          <span className="text-[10px] text-neutral-500 mr-1">
            <input
              type="checkbox"
              checked={selectedIds.size === items.length && items.length > 0}
              onChange={toggleSelectAll}
              className="mr-1.5 accent-green-500"
            />
            Select All ({selectedIds.size}/{items.length})
          </span>
          <button
            disabled={selectedIds.size === 0 || batchBusy}
            onClick={handleBatchApprove}
            className="text-[9px] px-2.5 py-1 bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {batchBusy ? '...' : `Approve Selected (${selectedIds.size})`}
          </button>
          <button
            disabled={selectedIds.size === 0 || batchBusy}
            onClick={handleBatchReject}
            className="text-[9px] px-2.5 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {batchBusy ? '...' : `Reject Selected (${selectedIds.size})`}
          </button>
          <div className="flex-1" />
          <button
            disabled={items.length === 0 || batchBusy}
            onClick={handleClearAll}
            className="text-[9px] px-2.5 py-1 bg-neutral-500/20 hover:bg-neutral-500/30 text-neutral-400 border border-neutral-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {batchBusy ? '...' : `Clear All (${items.length})`}
          </button>
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
                <th className="text-left px-3 py-2 text-neutral-600 uppercase tracking-wider w-8">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === items.length && items.length > 0}
                    onChange={toggleSelectAll}
                    className="accent-green-500"
                  />
                </th>
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
                  <td className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(it.id)}
                      onChange={() => toggleSelect(it.id)}
                      className="accent-green-500"
                    />
                  </td>
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
