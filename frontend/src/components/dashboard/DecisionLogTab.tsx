import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { DataTable, ColumnDef, FilterDef } from '../DataTable'
import { useTableQuery } from '../../hooks/useTableQuery'
import {
  fetchDecisions,
  fetchDecision,
  decisionsExportUrl,
  DecisionLogRow,
  DecisionLogDetail,
} from '../../api'

const DECISION_COLORS: Record<string, string> = {
  BUY: 'text-green-500',
  SELL: 'text-red-500',
  SKIP: 'text-neutral-500',
  HOLD: 'text-yellow-500',
}

const OUTCOME_COLORS: Record<string, string> = {
  WIN: 'text-green-500',
  LOSS: 'text-red-500',
  PUSH: 'text-yellow-500',
}

const COLUMNS: ColumnDef<DecisionLogRow>[] = [
  {
    key: 'id',
    label: 'ID',
    sortable: true,
    className: 'tabular-nums text-neutral-500 w-12',
  },
  {
    key: 'strategy',
    label: 'Strategy',
    sortable: true,
  },
  {
    key: 'market_ticker',
    label: 'Market',
    sortable: true,
    className: 'font-mono',
  },
  {
    key: 'decision',
    label: 'Decision',
    sortable: true,
    render: (_, value) => {
      const v = String(value ?? '')
      return (
        <span className={`uppercase font-bold ${DECISION_COLORS[v] ?? 'text-neutral-300'}`}>
          {v || '—'}
        </span>
      )
    },
  },
  {
    key: 'confidence',
    label: 'Confidence',
    sortable: true,
    className: 'tabular-nums',
    render: (_, value) => {
      if (value == null) return <span className="text-neutral-600">—</span>
      const pct = (Number(value) * 100).toFixed(1)
      return <span className="text-neutral-300">{pct}%</span>
    },
  },
  {
    key: 'reason',
    label: 'Reason',
    render: (_, value) => {
      const v = String(value ?? '')
      if (!v) return <span className="text-neutral-600">—</span>
      const truncated = v.length > 40 ? v.slice(0, 40) + '…' : v
      return <span className="text-neutral-400">{truncated}</span>
    },
  },
  {
    key: 'outcome',
    label: 'Outcome',
    render: (_, value) => {
      const v = String(value ?? '')
      if (!v) return <span className="text-neutral-600">—</span>
      return (
        <span className={`uppercase font-bold ${OUTCOME_COLORS[v] ?? 'text-neutral-300'}`}>
          {v}
        </span>
      )
    },
  },
  {
    key: 'created_at',
    label: 'Created',
    sortable: true,
    className: 'tabular-nums text-neutral-500',
    render: (_, value) => {
      if (!value) return <span className="text-neutral-600">—</span>
      return (
        <span>
          {new Date(String(value)).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })}
        </span>
      )
    },
  },
]

const FILTERS: FilterDef[] = [
  { key: 'strategy', label: 'Strategy', type: 'text', placeholder: 'filter strategy' },
  {
    key: 'decision',
    label: 'Decision',
    type: 'select',
    options: [
      { label: 'BUY', value: 'BUY' },
      { label: 'SELL', value: 'SELL' },
      { label: 'SKIP', value: 'SKIP' },
      { label: 'HOLD', value: 'HOLD' },
    ],
  },
  { key: 'market', label: 'Market', type: 'text', placeholder: 'filter ticker' },
  { key: 'since', label: 'Since', type: 'text', placeholder: 'YYYY-MM-DD' },
]

function DetailModal({
  id,
  onClose,
}: {
  id: number
  onClose: () => void
}) {
  const { data, isLoading } = useQuery<DecisionLogDetail>({
    queryKey: ['decision', id],
    queryFn: () => fetchDecision(id),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl border border-neutral-700 bg-neutral-950 max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="sticky top-0 bg-neutral-950 border-b border-neutral-800 px-4 py-2 flex items-center justify-between">
          <span className="text-[10px] text-neutral-400 uppercase tracking-wider">
            Decision #{id}
          </span>
          <button
            onClick={onClose}
            className="text-[10px] text-neutral-600 hover:text-neutral-300 transition-colors uppercase tracking-wider"
          >
            Close
          </button>
        </div>

        {isLoading ? (
          <div className="px-4 py-8 text-center text-[10px] text-neutral-600 uppercase tracking-wider">
            Loading...
          </div>
        ) : !data ? (
          <div className="px-4 py-8 text-center text-[10px] text-neutral-600">
            Not found
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Fields */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
              {(
                [
                  ['Strategy', data.strategy],
                  ['Market', data.market_ticker],
                  ['Decision', data.decision],
                  ['Confidence', data.confidence != null ? (Number(data.confidence) * 100).toFixed(1) + '%' : '—'],
                  ['Outcome', data.outcome ?? '—'],
                  ['Created', data.created_at ? new Date(data.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'],
                ] as [string, string][]
              ).map(([label, val]) => (
                <div key={label} className="flex flex-col gap-0.5">
                  <span className="text-[9px] text-neutral-600 uppercase tracking-wider">{label}</span>
                  <span className="text-[10px] font-mono text-neutral-300">{val}</span>
                </div>
              ))}
            </div>

            {/* Reason */}
            {data.reason && (
              <div className="flex flex-col gap-0.5">
                <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Reason</span>
                <span className="text-[10px] text-neutral-400">{data.reason}</span>
              </div>
            )}

            {/* Signal data */}
            <div className="flex flex-col gap-1">
              <span className="text-[9px] text-neutral-600 uppercase tracking-wider">Signal Data</span>
              <pre className="text-[10px] font-mono text-neutral-400 bg-black border border-neutral-800 p-3 overflow-x-auto whitespace-pre-wrap break-all">
                {data.signal_data != null
                  ? JSON.stringify(data.signal_data, null, 2)
                  : 'null'}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function DecisionLogTab() {
  const [detailId, setDetailId] = useState<number | null>(null)

  const { state, setSort, setFilter, setPage, currentPage, toQueryParams } = useTableQuery({
    defaultSort: 'created_at',
    defaultOrder: 'desc',
    defaultLimit: 50,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['decisions', state],
    queryFn: () => fetchDecisions(toQueryParams()),
    refetchInterval: 30000,
  })

  const columnsWithDetail: ColumnDef<DecisionLogRow>[] = [
    ...COLUMNS,
    {
      key: '_detail',
      label: '',
      render: row => (
        <button
          onClick={() => setDetailId(row.id as number)}
          className="text-[9px] text-neutral-600 hover:text-green-500 uppercase tracking-wider border border-neutral-800 hover:border-green-500/40 px-1.5 py-0.5 transition-colors"
        >
          Detail
        </button>
      ),
    },
  ]

  const handleClose = useCallback(() => setDetailId(null), [])

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4">
      <div className="border border-neutral-800">
        {/* Header */}
        <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between">
          <span className="text-[10px] text-neutral-500 uppercase tracking-wider">
            Decision Log
          </span>
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-neutral-600 tabular-nums">
              {data?.total ?? 0} total
            </span>
            <a
              href={decisionsExportUrl()}
              download
              className="text-[9px] text-neutral-600 hover:text-green-500 uppercase tracking-wider border border-neutral-800 hover:border-green-500/40 px-2 py-0.5 transition-colors"
            >
              Export JSONL
            </a>
          </div>
        </div>

        {/* Table */}
        <div className="p-3">
          <DataTable<DecisionLogRow>
            columns={columnsWithDetail}
            rows={data?.items ?? []}
            total={data?.total ?? 0}
            sort={state.sort}
            order={state.order}
            limit={state.limit}
            currentPage={currentPage}
            onSort={setSort}
            onPageChange={setPage}
            filters={FILTERS}
            filterValues={state.filters}
            onFilterChange={setFilter}
            loading={isLoading}
            emptyMessage="No decisions logged yet"
            keyField="id"
          />
        </div>
      </div>

      {detailId != null && (
        <DetailModal id={detailId} onClose={handleClose} />
      )}
    </div>
  )
}
