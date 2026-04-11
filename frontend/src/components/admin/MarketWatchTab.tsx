import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchMarketWatches, createMarketWatch, deleteMarketWatch } from '../../api'

export function MarketWatchTab() {
  const qc = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [category, setCategory] = useState('')
  const [adding, setAdding] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['market-watches'],
    queryFn: () => fetchMarketWatches(),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleDelete = async (id: number) => {
    await deleteMarketWatch(id)
    qc.invalidateQueries({ queryKey: ['market-watches'] })
  }

  const handleAdd = async () => {
    if (!ticker.trim()) return
    setAdding(true)
    try {
      await createMarketWatch({ ticker: ticker.trim(), category: category.trim() || undefined })
      setTicker('')
      setCategory('')
      qc.invalidateQueries({ queryKey: ['market-watches'] })
    } finally {
      setAdding(false)
    }
  }

  if (isLoading) return <div className="text-[10px] text-neutral-600">Loading market watches...</div>

  return (
    <div className="space-y-4">
      <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
        Market Watch — {total} total
      </div>
      <div className="border border-neutral-800">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="border-b border-neutral-800">
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Ticker</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Category</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Source</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Enabled</th>
              <th className="px-3 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {items.map(row => (
              <tr key={row.id} className="border-b border-neutral-800/50 hover:bg-neutral-900/30">
                <td className="px-3 py-1.5 text-neutral-300">{row.ticker}</td>
                <td className="px-3 py-1.5 text-neutral-500">{row.category || '—'}</td>
                <td className="px-3 py-1.5 text-neutral-500">{row.source || '—'}</td>
                <td className="px-3 py-1.5">
                  <span className={row.enabled ? 'text-green-500' : 'text-neutral-600'}>
                    {row.enabled ? 'yes' : 'no'}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    onClick={() => handleDelete(row.id)}
                    className="text-red-600 hover:text-red-400 transition-colors text-[11px] leading-none"
                    title="Delete"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-3 text-neutral-700 text-center">No market watches configured</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="border border-neutral-800 p-3">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Add Market Watch</div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="Ticker"
            className="bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none w-48 placeholder:text-neutral-700"
          />
          <input
            type="text"
            value={category}
            onChange={e => setCategory(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="Category (optional)"
            className="bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none w-48 placeholder:text-neutral-700"
          />
          <button
            onClick={handleAdd}
            disabled={adding || !ticker.trim()}
            className="px-3 py-1 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
          >
            {adding ? 'Adding...' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  )
}
