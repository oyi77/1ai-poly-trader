import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { DataTable } from '../DataTable'
import type { ColumnDef, FilterDef } from '../DataTable'
import {
  fetchHealth,
  fetchStrategies,
  updateStrategy,
  runStrategyNow,
  fetchMarketWatches,
  createMarketWatch,
  deleteMarketWatch,
} from '../../api'
import { AdminOnly } from '../AdminOnly'

// ── Strategy Health ───────────────────────────────────────────────────────────

function HealthSection() {
  const { data, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 15000,
  })

  return (
    <div className="border border-neutral-800">
      <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Strategy Health</span>
        <div className="flex items-center gap-2">
          {data != null && (
            <span className={`text-[9px] uppercase tracking-wider ${data.bot_running ? 'text-green-500' : 'text-red-500'}`}>
              Bot {data.bot_running ? 'Running' : 'Stopped'}
            </span>
          )}
          <span className="text-[9px] text-neutral-600">15s refresh</span>
        </div>
      </div>

      {isLoading ? (
        <div className="px-3 py-8 text-center text-[10px] text-neutral-600 uppercase tracking-wider">Loading...</div>
      ) : !data?.strategies?.length ? (
        <div className="px-3 py-8 text-center text-[10px] text-neutral-600">No strategies found</div>
      ) : (
        <div className="grid grid-cols-2 gap-px bg-neutral-800 md:grid-cols-3 lg:grid-cols-4">
          {data.strategies.map(s => (
            <div key={s.name} className="bg-black px-3 py-2.5 flex flex-col gap-1">
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.healthy ? 'bg-green-500' : 'bg-red-500'}`}
                />
                <span className="text-[10px] text-neutral-300 font-mono truncate">{s.name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className={`text-[9px] uppercase tracking-wider ${s.healthy ? 'text-green-500' : 'text-red-500'}`}>
                  {s.healthy ? 'Healthy' : 'Stale'}
                </span>
                {s.lag_seconds != null && (
                  <span className="text-[9px] text-neutral-600 tabular-nums">
                    {s.lag_seconds < 60
                      ? `${s.lag_seconds}s`
                      : `${Math.floor(s.lag_seconds / 60)}m ${s.lag_seconds % 60}s`} lag
                  </span>
                )}
              </div>
              {s.last_heartbeat && (
                <span className="text-[9px] text-neutral-700 tabular-nums truncate">
                  {new Date(s.last_heartbeat).toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                  })}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Active Strategies ─────────────────────────────────────────────────────────

function StrategiesSection() {
  const queryClient = useQueryClient()
  const [flashMap, setFlashMap] = useState<Record<string, boolean>>({})

  const { data: strategies, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    refetchInterval: 30000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      updateStrategy(name, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const runNowMutation = useMutation({
    mutationFn: (name: string) => runStrategyNow(name),
    onSuccess: (_data, name) => {
      setFlashMap(prev => ({ ...prev, [name]: true }))
      setTimeout(() => {
        setFlashMap(prev => {
          const next = { ...prev }
          delete next[name]
          return next
        })
      }, 2000)
    },
  })

  return (
    <div className="border border-neutral-800">
      <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Active Strategies</span>
        <span className="text-[9px] text-neutral-600">30s refresh</span>
      </div>

      {isLoading ? (
        <div className="px-3 py-8 text-center text-[10px] text-neutral-600 uppercase tracking-wider">Loading...</div>
      ) : !strategies?.length ? (
        <div className="px-3 py-8 text-center text-[10px] text-neutral-600">No strategies configured</div>
      ) : (
        <div className="divide-y divide-neutral-900">
          {strategies.map(s => (
            <div key={s.name} className="px-3 py-2 flex items-center gap-3 hover:bg-neutral-900/30 transition-colors">
              <AdminOnly
                fallback={<span className={`w-2 h-2 rounded-full shrink-0 ${s.enabled ? 'bg-green-500' : 'bg-neutral-600'}`} title={s.enabled ? 'Enabled' : 'Disabled'} />}
              >
                <button
                  onClick={() => toggleMutation.mutate({ name: s.name, enabled: !s.enabled })}
                  disabled={toggleMutation.isPending}
                  className={`w-7 h-4 rounded-sm border flex items-center transition-colors flex-shrink-0 ${
                    s.enabled
                      ? 'border-green-700 bg-green-900/40'
                      : 'border-neutral-700 bg-neutral-900'
                  }`}
                  title={s.enabled ? 'Disable' : 'Enable'}
                >
                  <span
                    className={`w-3 h-3 rounded-sm transition-transform flex-shrink-0 ${
                      s.enabled ? 'bg-green-500 translate-x-3.5' : 'bg-neutral-600 translate-x-0.5'
                    }`}
                  />
                </button>
              </AdminOnly>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-neutral-300 font-mono">{s.name}</span>
                  <span className="text-[9px] text-neutral-600 uppercase tracking-wider">{s.category}</span>
                </div>
                {s.description && (
                  <span className="text-[9px] text-neutral-600 truncate block">{s.description}</span>
                )}
              </div>

              {/* Interval */}
              <span className="text-[9px] text-neutral-600 tabular-nums flex-shrink-0">
                {s.interval_seconds >= 3600
                  ? `${(s.interval_seconds / 3600).toFixed(0)}h`
                  : s.interval_seconds >= 60
                  ? `${(s.interval_seconds / 60).toFixed(0)}m`
                  : `${s.interval_seconds}s`}
              </span>

              <AdminOnly>
                <button
                  onClick={() => runNowMutation.mutate(s.name)}
                  disabled={runNowMutation.isPending}
                  className={`px-2 py-0.5 text-[9px] border transition-colors flex-shrink-0 ${
                    flashMap[s.name]
                      ? 'border-green-600 text-green-500'
                      : 'border-neutral-700 text-neutral-500 hover:border-neutral-500 hover:text-neutral-300'
                  }`}
                >
                  {flashMap[s.name] ? 'Done' : 'Run Now'}
                </button>
              </AdminOnly>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Market Watch ──────────────────────────────────────────────────────────────

const MARKET_WATCH_COLUMNS: ColumnDef<Record<string, unknown>>[] = [
  { key: 'ticker', label: 'Ticker', sortable: true },
  { key: 'category', label: 'Category' },
  { key: 'source', label: 'Source' },
  {
    key: 'enabled',
    label: 'Enabled',
    render: (_row, value) => (
      <span className={value ? 'text-green-500' : 'text-neutral-600'}>
        {value ? 'Yes' : 'No'}
      </span>
    ),
  },
  {
    key: 'created_at',
    label: 'Created',
    render: (_row, value) =>
      value
        ? new Date(value as string).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })
        : '—',
  },
]

const MARKET_WATCH_FILTERS: FilterDef[] = [
  { key: 'q', label: 'Search', type: 'text', placeholder: 'ticker...' },
  {
    key: 'enabled',
    label: 'Enabled',
    type: 'select',
    options: [
      { label: 'Yes', value: 'true' },
      { label: 'No', value: 'false' },
    ],
  },
  { key: 'category', label: 'Category', type: 'text', placeholder: 'category...' },
]

function MarketWatchSection() {
  const queryClient = useQueryClient()
  const [filterValues, setFilterValues] = useState<Record<string, string>>({})
  const [newTicker, setNewTicker] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  const buildParams = () => {
    const p: Record<string, string | number | boolean> = {}
    if (filterValues.q) p.q = filterValues.q
    if (filterValues.enabled !== '' && filterValues.enabled != null)
      p.enabled = filterValues.enabled === 'true'
    if (filterValues.category) p.category = filterValues.category
    return p
  }

  const { data, isLoading } = useQuery({
    queryKey: ['market-watches', filterValues],
    queryFn: () => fetchMarketWatches(buildParams()),
    refetchInterval: 30000,
  })

  const createMutation = useMutation({
    mutationFn: (body: { ticker: string; category?: string }) => createMarketWatch(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['market-watches'] })
      setNewTicker('')
      setNewCategory('')
      setAddError(null)
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Failed to add watch'
      setAddError(msg)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteMarketWatch(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['market-watches'] })
    },
  })

  const handleFilterChange = (key: string, value: string) => {
    setFilterValues(prev => ({ ...prev, [key]: value }))
  }

  const handleAdd = () => {
    const ticker = newTicker.trim().toUpperCase()
    if (!ticker) return
    createMutation.mutate({
      ticker,
      category: newCategory.trim() || undefined,
    })
  }

  const columnsWithDelete: ColumnDef<Record<string, unknown>>[] = [
    ...MARKET_WATCH_COLUMNS,
    {
      key: 'id',
      label: '',
      className: 'w-6',
      render: (row) => (
        <AdminOnly>
          <button
            onClick={() => deleteMutation.mutate(row.id as number)}
            disabled={deleteMutation.isPending}
            className="text-[10px] text-red-700 hover:text-red-500 transition-colors px-1"
            title="Remove watch"
          >
            ×
          </button>
        </AdminOnly>
      ),
    },
  ]

  const rows = (data?.items ?? []) as unknown as Record<string, unknown>[]

  return (
    <div className="border border-neutral-800">
      <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Market Watch</span>
        <span className="text-[10px] text-neutral-600 tabular-nums">
          {data?.total ?? 0} entries
        </span>
      </div>

      <AdminOnly fallback={<div className="px-3 py-2 border-b border-neutral-800 text-[10px] text-neutral-600 uppercase tracking-wider">Public read-only market watch</div>}>
      <div className="px-3 py-2 border-b border-neutral-800 flex items-end gap-2 flex-wrap">
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Ticker</span>
          <input
            value={newTicker}
            onChange={e => setNewTicker(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="e.g. BTC-USD"
            className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:border-neutral-500 focus:outline-none w-32"
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Category</span>
          <input
            value={newCategory}
            onChange={e => setNewCategory(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="crypto, weather…"
            className="bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-0.5 font-mono focus:border-neutral-500 focus:outline-none w-28"
          />
        </div>
        <button
          onClick={handleAdd}
          disabled={!newTicker.trim() || createMutation.isPending}
          className="px-3 py-0.5 text-[10px] border border-green-800 text-green-500 hover:border-green-600 disabled:opacity-30 transition-colors"
        >
          {createMutation.isPending ? 'Adding…' : 'Watch'}
        </button>
        {addError && (
          <span className="text-[9px] text-red-500">{addError}</span>
        )}
      </div>
      </AdminOnly>

      <div className="px-3 py-3">
        <DataTable
          columns={columnsWithDelete}
          rows={rows}
          total={data?.total ?? 0}
          loading={isLoading}
          filters={MARKET_WATCH_FILTERS}
          filterValues={filterValues}
          onFilterChange={handleFilterChange}
          emptyMessage="No markets being watched"
          keyField="id"
        />
      </div>
    </div>
  )
}

// ── Tab Component ──────────────────────────────────────────────────────────────

export function MarketIntelTab() {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      <HealthSection />
      <StrategiesSection />
      <MarketWatchSection />
    </div>
  )
}
