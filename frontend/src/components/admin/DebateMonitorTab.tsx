import { POLL } from '../../polling'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchDecisions,
  fetchDecision,
  DecisionLogRow,
  DecisionLogDetail,
} from '../../api'
import { DataTable, ColumnDef } from '../DataTable'
import { useTableQuery } from '../../hooks/useTableQuery'
import { Loader2, MessagesSquare, ChevronRight, ShieldCheck, X } from 'lucide-react'

const DECISION_COLORS: Record<string, string> = {
  BUY: 'text-green-500',
  SELL: 'text-red-500',
  SKIP: 'text-neutral-500',
  HOLD: 'text-yellow-500',
}

const COLUMNS: ColumnDef<DecisionLogRow>[] = [
  {
    key: 'id',
    label: 'ID',
    sortable: true,
    className: 'tabular-nums text-neutral-500 w-12',
  },
  {
    key: 'market_ticker',
    label: 'Market',
    sortable: true,
    className: 'font-mono text-xs max-w-[150px] truncate',
  },
  {
    key: 'decision',
    label: 'Decision',
    sortable: true,
    render: (_, value) => {
      const v = String(value ?? '')
      const color = DECISION_COLORS[v] || 'text-neutral-300'
      return <span className={color}>{v}</span>
    },
  },
  {
    key: 'confidence',
    label: 'Conf %',
    sortable: true,
    className: 'tabular-nums text-right w-16',
    render: (row) => {
      // Extract actual debate confidence from signal_data if available
      const signalData = (row as any).signal_data
      const debateConf = signalData?.debate_transcript?.debate_transcript?.judge?.confidence
      const displayConf = debateConf ?? row.confidence
      return displayConf != null ? `${(Number(displayConf) * 100).toFixed(1)}%` : '-'
    },
  },
  {
    key: 'created_at',
    label: 'Time',
    sortable: true,
    className: 'tabular-nums text-neutral-500 w-28 text-right',
    render: (_, value) => (value ? new Date(String(value)).toLocaleTimeString() : '-'),
  },
]

function DebateTranscriptView({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery<DecisionLogDetail>({
    queryKey: ['decision', id],
    queryFn: () => fetchDecision(id),
  })

  if (isLoading) return <div className="p-8 flex items-center justify-center text-neutral-500 gap-3"><Loader2 className="w-5 h-5 animate-spin" /> <span className="uppercase tracking-widest text-[10px]">Loading transcript...</span></div>
  if (error) return <div className="p-8 text-center text-red-500 uppercase tracking-widest text-[10px]">Failed to load detail</div>
  if (!data) return <div className="p-8 text-center text-neutral-500 uppercase tracking-widest text-[10px]">No data found.</div>

  const signalData = data.signal_data
  if (!signalData || !signalData.debate_transcript) {
    return (
      <div className="p-8 text-neutral-500 flex flex-col items-center justify-center gap-4 text-center">
        <p className="uppercase tracking-widest text-xs text-neutral-400">No debate transcript recorded for this decision.</p>
        <p className="text-[10px] font-mono bg-neutral-900 p-4 rounded-sm border border-neutral-800 max-w-lg break-words text-left w-full">
          {JSON.stringify(signalData?.reasoning || data.reason || 'No reasoning')}
        </p>
      </div>
    )
  }

  // The structure returned by to_transcript_dict()
  interface DebateTranscript {
    debate_transcript?: DebateTranscript
    bull_arguments?: Array<{ round: number; probability?: number; reasoning?: string; raw_response?: string }>
    bear_arguments?: Array<{ round: number; probability?: number; reasoning?: string; raw_response?: string }>
    judge?: { reasoning?: string; raw_response?: string; consensus_probability?: number; confidence?: number }
    data_sources?: Array<string | { title?: string; name?: string; url?: string }>
  }
  const tWrapper = signalData.debate_transcript as DebateTranscript | undefined
  const transcript = tWrapper?.debate_transcript || tWrapper
  const bulls = transcript?.bull_arguments || []
  const bears = transcript?.bear_arguments || []
  const judge = transcript?.judge
  const dataSources = tWrapper?.data_sources || (signalData.data_sources as Array<string | { title?: string; name?: string; url?: string }>) || []

  return (
    <div className="p-4 space-y-6 bg-black text-[10px]">
      
      {/* JUDGE SYNTHESIS (Top Level Highlight) */}
      {judge && (
        <div className="border border-green-500/30 bg-green-500/5 p-4 rounded-sm shadow-[0_0_15px_rgba(34,197,94,0.05)]">
          <div className="flex items-center gap-2 mb-3 text-green-400 font-bold uppercase tracking-wider text-xs">
            <ShieldCheck className="w-4 h-4" /> Judge Synthesis
          </div>
          <div className="text-neutral-200 leading-relaxed font-mono whitespace-pre-wrap text-sm">
            {judge.reasoning || judge.raw_response}
          </div>
          <div className="mt-4 flex gap-6 text-neutral-400 font-mono border-t border-green-500/20 pt-3">
            <span className="flex items-center gap-2">
              <span className="text-neutral-500">Consensus Prob:</span> 
              <span className="text-green-400">{judge.consensus_probability != null ? `${(judge.consensus_probability * 100).toFixed(1)}%` : 'N/A'}</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="text-neutral-500">Confidence:</span>
              <span className="text-green-400">{judge.confidence != null ? `${(judge.confidence * 100).toFixed(1)}%` : 'N/A'}</span>
            </span>
          </div>
        </div>
      )}

      {/* DEBATE ROUNDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* BULLS */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-emerald-500 font-bold uppercase tracking-widest border-b border-emerald-500/20 pb-2 mb-4">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            Bull Arguments
          </div>
          {bulls.length === 0 && <div className="text-neutral-600 italic">No bull arguments.</div>}
          {bulls.map((arg: any, i: number) => (
            <div key={i} className="bg-neutral-900/80 border border-emerald-500/20 p-4 rounded-sm hover:border-emerald-500/40 transition-colors">
              <div className="flex justify-between items-center text-[9px] text-emerald-500/70 mb-2 uppercase font-bold tracking-wider">
                <span className="bg-emerald-500/10 px-2 py-0.5 rounded-sm">Round {arg.round}</span>
                <span>Prob: {arg.probability ? `${(arg.probability * 100).toFixed(1)}%` : 'N/A'}</span>
              </div>
              <div className="text-neutral-300 font-mono whitespace-pre-wrap leading-relaxed">
                {arg.reasoning || arg.raw_response}
              </div>
            </div>
          ))}
        </div>

        {/* BEARS */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-rose-500 font-bold uppercase tracking-widest border-b border-rose-500/20 pb-2 mb-4">
            <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></div>
            Bear Arguments
          </div>
          {bears.length === 0 && <div className="text-neutral-600 italic">No bear arguments.</div>}
          {bears.map((arg: any, i: number) => (
            <div key={i} className="bg-neutral-900/80 border border-rose-500/20 p-4 rounded-sm hover:border-rose-500/40 transition-colors">
              <div className="flex justify-between items-center text-[9px] text-rose-500/70 mb-2 uppercase font-bold tracking-wider">
                <span className="bg-rose-500/10 px-2 py-0.5 rounded-sm">Round {arg.round}</span>
                <span>Prob: {arg.probability ? `${(arg.probability * 100).toFixed(1)}%` : 'N/A'}</span>
              </div>
              <div className="text-neutral-300 font-mono whitespace-pre-wrap leading-relaxed">
                {arg.reasoning || arg.raw_response}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* DATA SOURCES */}
      {dataSources && dataSources.length > 0 && (
        <div className="pt-6 mt-6 border-t border-neutral-800">
          <div className="text-neutral-400 font-bold uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-neutral-600"></span>
            Data Sources
          </div>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-neutral-400 font-mono text-[9px]">
            {dataSources.map((ds: any, i: number) => (
              <li key={i} className="bg-neutral-900/50 p-2 rounded-sm border border-neutral-800 truncate">
                {typeof ds === 'string' ? (
                  ds.startsWith('http') ? <a href={ds} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline">{ds}</a> : ds
                ) : (
                  <span className="flex flex-col gap-1">
                    <span className="text-neutral-300 font-semibold">{ds.title || ds.name || 'Source'}</span>
                    {ds.url ? <a href={ds.url} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 hover:underline truncate">{ds.url}</a> : <span className="text-neutral-600 truncate">{JSON.stringify(ds)}</span>}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function DebateMonitorTab() {
  const [selectedDecisionId, setSelectedDecisionId] = useState<number | null>(null)

  const { state, setSort, toQueryParams } = useTableQuery({
    defaultSort: 'created_at',
    defaultOrder: 'desc',
    defaultLimit: 50,
  })

  // We explicitly want to view ai driven strategies, particularly general_scanner
  const queryParams = { ...toQueryParams(), strategy: 'general_scanner' }

  const { data, isLoading, error } = useQuery({
    queryKey: ['decisions', queryParams],
    queryFn: () => fetchDecisions(queryParams),
    refetchInterval: POLL.SLOW,
  })

  const handleRowClick = (row: DecisionLogRow) => {
    setSelectedDecisionId(prev => (prev === row.id ? null : row.id))
  }

  const columnsWithAction: ColumnDef<DecisionLogRow>[] = [
    ...COLUMNS,
    {
      key: '_action',
      label: '',
      className: 'w-10 text-right',
      render: row => {
        const isSelected = selectedDecisionId === row.id
        return (
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleRowClick(row)
            }}
            className={`transition-colors p-1.5 rounded-sm ${isSelected ? 'bg-emerald-500/20 text-emerald-400' : 'text-neutral-500 hover:text-white hover:bg-neutral-800'}`}
            title="View Debate Room"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )
      },
    },
  ]

  if (error) {
    return <div className="p-6 text-red-500 border border-red-500/20 bg-red-500/5 rounded-sm">Failed to load debate history.</div>
  }

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] min-h-[600px] overflow-hidden bg-black text-neutral-200">
      <div className="flex-none pb-4 border-b border-neutral-800 mb-4 px-2 pt-2">
        <h2 className="text-xl font-bold text-neutral-100 tracking-wider flex items-center gap-3 uppercase">
          <div className="p-2 bg-emerald-500/10 rounded-sm">
            <MessagesSquare className="w-5 h-5 text-emerald-500" />
          </div>
          AI Debate Monitor
        </h2>
        <p className="text-[10px] text-neutral-500 uppercase tracking-widest mt-2 ml-12">
          Real-time transcript analysis from General Market Scanner
        </p>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-6 overflow-hidden pb-4">
        {/* Left Panel: List */}
        <div className="w-full md:w-1/2 lg:w-5/12 xl:w-1/3 flex flex-col border border-neutral-800 bg-neutral-900/30 rounded-sm overflow-hidden">
          <div className="p-3 border-b border-neutral-800 bg-neutral-900/80">
            <h3 className="text-xs font-bold text-neutral-300 uppercase tracking-widest">Recent Debates</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-neutral-700 scrollbar-track-transparent">
            <DataTable
              rows={data?.items || []}
              columns={columnsWithAction}
              loading={isLoading}
              sort={state.sort}
              order={state.order}
              onSort={setSort}
            />
          </div>
        </div>

        {/* Right Panel: Debate Room */}
        <div className="w-full md:flex-1 flex flex-col border border-neutral-800 bg-black rounded-sm overflow-hidden shadow-2xl relative">
          {selectedDecisionId ? (
            <>
              <div className="flex items-center justify-between bg-neutral-900/90 border-b border-neutral-800 px-5 py-3 sticky top-0 z-10 backdrop-blur-sm">
                <span className="text-xs uppercase font-bold tracking-widest text-emerald-400 flex items-center gap-3">
                  <MessagesSquare className="w-4 h-4" />
                  Debate Room <span className="text-neutral-600 font-normal">|</span> <span className="font-mono text-neutral-300">#{selectedDecisionId}</span>
                </span>
                <button 
                  onClick={() => setSelectedDecisionId(null)}
                  className="text-neutral-500 hover:text-white hover:bg-neutral-800 p-1.5 rounded-sm transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-neutral-700 scrollbar-track-transparent bg-gradient-to-b from-black to-neutral-950">
                <DebateTranscriptView id={selectedDecisionId} />
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-neutral-600 space-y-6 p-8 text-center bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-neutral-900/20 via-black to-black">
              <div className="w-20 h-20 rounded-full border border-neutral-800 flex items-center justify-center bg-neutral-900/30">
                <MessagesSquare className="w-8 h-8 text-neutral-700" />
              </div>
              <div className="space-y-2">
                <h3 className="uppercase tracking-widest text-xs font-bold text-neutral-400">Debate Room Empty</h3>
                <p className="text-[10px] font-mono text-neutral-500 max-w-[250px]">Select a debate from the list to view the full AI transcript, bull/bear arguments, and judge synthesis.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
