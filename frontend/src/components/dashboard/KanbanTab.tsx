import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { POLL } from '../../polling'
import { fetchKanbanBoard, moveKanbanCard } from '../../api'
import type { KanbanCard } from '../../types'

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  return `$${v.toFixed(2)}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

const COLUMN_ACCENT: Record<string, string> = {
  backtest: 'border-blue-500/30 bg-blue-500/5',
  shadow: 'border-purple-500/30 bg-purple-500/5',
  paper: 'border-amber-500/30 bg-amber-500/5',
  live_promoted: 'border-green-500/30 bg-green-500/5',
  review: 'border-red-500/30 bg-red-500/5',
  retired: 'border-neutral-600/30 bg-neutral-800/30',
}

const COLUMN_HEADER_ACCENT: Record<string, string> = {
  backtest: 'text-blue-400',
  shadow: 'text-purple-400',
  paper: 'text-amber-400',
  live_promoted: 'text-green-400',
  review: 'text-red-400',
  retired: 'text-neutral-500',
}

const MOVE_OPTIONS: Record<string, { label: string; target: string }[]> = {
  backtest: [{ label: '→ Shadow', target: 'shadow' }],
  shadow: [{ label: '→ Paper', target: 'paper' }, { label: '→ Backtest', target: 'backtest' }],
  paper: [{ label: '→ Live', target: 'live_promoted' }, { label: '→ Review', target: 'review' }],
  live_promoted: [{ label: '→ Review', target: 'review' }, { label: '→ Retire', target: 'retired' }],
  review: [{ label: '→ Backtest', target: 'backtest' }, { label: '→ Retire', target: 'retired' }],
  retired: [{ label: '→ Review', target: 'review' }],
}

function KanbanCardComponent({
  card,
  isAdmin,
  onMove,
  moving,
}: {
  card: KanbanCard
  isAdmin: boolean
  onMove: (id: number, target: string, reason?: string) => void
  moving: string | null
}) {
  const [reasonInput, setReasonInput] = useState('')
  const [showReason, setShowReason] = useState<string | null>(null)

  const moveOptions = MOVE_OPTIONS[card.column] ?? []
  const isMoving = moving === card.id

  const handleMove = (target: string) => {
    if (target === 'review' || target === 'retired') {
      setShowReason(target)
    } else {
      onMove(Number(card.id), target)
    }
  }

  const confirmReasonMove = () => {
    onMove(Number(card.id), showReason!, reasonInput || undefined)
    setShowReason(null)
    setReasonInput('')
  }

  return (
    <div className={`border ${COLUMN_ACCENT[card.column] ?? 'border-neutral-700 bg-neutral-900'} rounded p-2.5 text-[10px] font-mono`}>
      <div className="flex items-start justify-between gap-1 mb-1.5">
        <div className="text-neutral-200 font-bold truncate" title={card.name}>{card.name}</div>
        <span className="shrink-0 px-1 py-0.5 border border-neutral-700 bg-neutral-900 text-neutral-500 text-[8px] uppercase tracking-wider">
          {card.strategy_name}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px] mb-1.5">
        {card.backtest_sharpe != null && (
          <>
            <span className="text-neutral-600">BT Sharpe</span>
            <span className={`text-right ${card.backtest_sharpe > 0 ? 'text-green-400' : 'text-red-400'}`}>{card.backtest_sharpe.toFixed(2)}</span>
          </>
        )}
        {card.backtest_win_rate != null && (
          <>
            <span className="text-neutral-600">BT Win%</span>
            <span className="text-right text-neutral-300">{fmtPct(card.backtest_win_rate)}</span>
          </>
        )}
        {card.shadow_trades != null && (
          <>
            <span className="text-neutral-600">Shadow Trades</span>
            <span className="text-right text-neutral-300">{card.shadow_trades}</span>
          </>
        )}
        {card.shadow_win_rate != null && (
          <>
            <span className="text-neutral-600">Shadow Win%</span>
            <span className="text-right text-neutral-300">{fmtPct(card.shadow_win_rate)}</span>
          </>
        )}
        {card.shadow_pnl != null && (
          <>
            <span className="text-neutral-600">Shadow PnL</span>
            <span className={`text-right ${(card.shadow_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{fmtMoney(card.shadow_pnl)}</span>
          </>
        )}
        {card.degradation_count > 0 && (
          <>
            <span className="text-neutral-600">Degradations</span>
            <span className="text-right text-red-400">{card.degradation_count}</span>
          </>
        )}
      </div>

      {card.review_reason && (
        <div className="text-red-400/80 text-[9px] mb-1.5 border-t border-red-500/20 pt-1.5">
          {card.review_reason}
        </div>
      )}

      <div className="text-neutral-700 text-[8px] mb-2">{fmtDate(card.created_at)}</div>

      {isAdmin && moveOptions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {moveOptions.map(opt => (
            <button
              key={opt.target}
              type="button"
              onClick={() => handleMove(opt.target)}
              disabled={isMoving}
              className="px-1.5 py-0.5 border border-neutral-700 bg-neutral-900 text-neutral-400 text-[8px] uppercase tracking-wider hover:bg-neutral-800 hover:text-neutral-200 disabled:opacity-40 transition-colors"
            >
              {isMoving ? '…' : opt.label}
            </button>
          ))}
        </div>
      )}

      {showReason && (
        <div className="mt-2 border border-amber-500/20 bg-amber-500/5 p-2">
          <div className="text-[9px] text-amber-300 mb-1">Reason (optional):</div>
          <input
            type="text"
            value={reasonInput}
            onChange={e => setReasonInput(e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-700 text-neutral-200 text-[10px] px-2 py-1 mb-1.5 focus:outline-none focus:border-amber-500/50"
            placeholder="e.g. Performance degradation..."
          />
          <div className="flex gap-1">
            <button type="button" onClick={confirmReasonMove} disabled={isMoving} className="px-2 py-0.5 border border-amber-500/40 bg-amber-500/15 text-amber-300 text-[8px] uppercase tracking-wider hover:bg-amber-500/25 disabled:opacity-40">
              Confirm
            </button>
            <button type="button" onClick={() => setShowReason(null)} className="px-2 py-0.5 border border-neutral-700 text-neutral-500 text-[8px] uppercase tracking-wider hover:text-neutral-300">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface KanbanTabProps {
  isAdmin?: boolean
}

export function KanbanTab({ isAdmin = false }: KanbanTabProps) {
  const queryClient = useQueryClient()
  const [movingCard, setMovingCard] = useState<string | null>(null)

  const board = useQuery({
    queryKey: ['kanban-board'],
    queryFn: fetchKanbanBoard,
    refetchInterval: POLL.SLOW,
  })

  const moveMutation = useMutation({
    mutationFn: ({ id, target, reason }: { id: number; target: string; reason?: string }) =>
      moveKanbanCard(id, target, reason),
    onMutate: (vars) => setMovingCard(String(vars.id)),
    onSettled: () => setMovingCard(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kanban-board'] }),
  })

  const handleMove = useCallback((id: number, target: string, reason?: string) => {
    moveMutation.mutate({ id, target, reason })
  }, [moveMutation])

  if (board.isLoading) return <div className="flex items-center justify-center h-full text-neutral-500 text-sm">Loading AGI Pipeline...</div>
  if (board.error) return <div className="flex items-center justify-center h-full text-red-500/70 text-sm">Failed to load AGI Pipeline</div>

  const columns = board.data?.columns ?? []

  return (
    <div className="h-full min-h-0 flex flex-col bg-black">
      <div className="shrink-0 border-b border-neutral-800 bg-neutral-950 px-3 py-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="text-xs font-bold text-neutral-100 uppercase tracking-widest font-mono">AGI Pipeline</div>
            <div className="text-[10px] text-neutral-600 mt-0.5">Strategy experiment lifecycle — Backtest → Shadow → Paper → Live</div>
          </div>
          <div className="flex-1" />
          <span className="text-[10px] text-neutral-600 font-mono">{board.data?.total_experiments ?? 0} experiments</span>
          {!isAdmin && (
            <span className="px-2 py-1 border border-neutral-800 bg-neutral-950 text-neutral-600 text-[10px] font-mono uppercase tracking-wider">
              Public read-only
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden">
        <div className="flex gap-3 p-3 h-full min-w-max">
          {columns.map(col => (
            <div key={col.id} className="flex flex-col w-64 min-w-[240px]">
              <div className="shrink-0 flex items-center justify-between px-2 py-1.5 mb-2 border-b border-neutral-800">
                <span className={`text-[10px] font-bold uppercase tracking-widest font-mono ${COLUMN_HEADER_ACCENT[col.id] ?? 'text-neutral-400'}`}>
                  {col.label}
                </span>
                <span className="text-[9px] text-neutral-600 font-mono">{col.cards.length}</span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
                {col.cards.map(card => (
                  <KanbanCardComponent
                    key={card.id}
                    card={card}
                    isAdmin={isAdmin}
                    onMove={handleMove}
                    moving={movingCard}
                  />
                ))}
                {col.cards.length === 0 && (
                  <div className="text-center text-neutral-700 text-[10px] py-8 font-mono">No experiments</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
