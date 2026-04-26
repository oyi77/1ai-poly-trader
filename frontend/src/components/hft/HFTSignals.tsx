import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowUpDown, ArrowUp, ArrowDown, Zap, Anchor, Fish, TrendingUp } from 'lucide-react'

interface HFTSignal {
  id: string
  type: 'edge' | 'arbitrage' | 'whale' | 'orderbook'
  strategy: string
  market: string
  direction: 'buy' | 'sell'
  confidence: number
  latency_ms: number
  edge_pct: number
  size_usd: number
  timestamp: string
  status: 'pending' | 'executed' | 'rejected'
  reason?: string
}

interface Props {
  maxRows?: number
}

function TypeBadge({ type }: { type: HFTSignal['type'] }) {
  const config = {
    edge: { icon: TrendingUp, cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20', label: 'EDGE' },
    arbitrage: { icon: Anchor, cls: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', label: 'ARB' },
    whale: { icon: Fish, cls: 'bg-purple-500/10 text-purple-400 border-purple-500/20', label: 'WHALE' },
    orderbook: { icon: Zap, cls: 'bg-green-500/10 text-green-400 border-green-500/20', label: 'OB' },
  }
  const c = config[type]
  return (
    <span className={`inline-flex items-center gap-0.5 text-[8px] font-bold px-1 py-0.5 border ${c.cls}`}>
      <c.icon className="w-2.5 h-2.5" />
      {c.label}
    </span>
  )
}

function LatencyBar({ ms }: { ms: number }) {
  const pct = Math.min(100, (ms / 100) * 100)
  const color = ms < 50 ? '#22c55e' : ms < 100 ? '#eab308' : '#ef4444'
  return (
    <div className="w-8 h-1.5 bg-neutral-800 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  )
}

function StatusBadge({ status }: { status: HFTSignal['status'] }) {
  const cls = status === 'executed' ? 'text-green-500' : status === 'rejected' ? 'text-red-500' : 'text-yellow-500'
  return <span className={`text-[9px] font-semibold uppercase ${cls}`}>{status}</span>
}

const MOCK_SIGNALS: HFTSignal[] = [
  { id: '1', type: 'edge', strategy: 'universal_scanner', market: 'btc-updown-5m', direction: 'buy', confidence: 0.82, latency_ms: 45, edge_pct: 5.2, size_usd: 25, timestamp: new Date().toISOString(), status: 'executed' },
  { id: '2', type: 'arbitrage', strategy: 'probability_arb', market: 'will-fed-cut-june', direction: 'buy', confidence: 1.0, latency_ms: 28, edge_pct: 8.1, size_usd: 50, timestamp: new Date().toISOString(), status: 'executed' },
  { id: '3', type: 'whale', strategy: 'whale_frontrun', market: 'trump-trial-verdict', direction: 'sell', confidence: 0.91, latency_ms: 67, edge_pct: 3.4, size_usd: 100, timestamp: new Date().toISOString(), status: 'pending' },
  { id: '4', type: 'orderbook', strategy: 'orderbook_hft', market: 'btc-100k-endyear', direction: 'buy', confidence: 0.74, latency_ms: 12, edge_pct: 2.1, size_usd: 10, timestamp: new Date().toISOString(), status: 'executed' },
  { id: '5', type: 'arbitrage', strategy: 'cross_market_arb', market: 'election-winner', direction: 'buy', confidence: 0.95, latency_ms: 89, edge_pct: 4.5, size_usd: 75, timestamp: new Date().toISOString(), status: 'rejected', reason: 'circuit_open' },
]

export function HFTSignals({ maxRows = 10 }: Props) {
  const [sortKey, setSortKey] = useState<'latency' | 'edge' | 'confidence' | 'size'>('latency')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const signals = MOCK_SIGNALS

  const sorted = useMemo(() => {
    return [...signals].sort((a, b) => {
      let aVal: number, bVal: number
      switch (sortKey) {
        case 'latency': aVal = a.latency_ms; bVal = b.latency_ms; break
        case 'edge': aVal = a.edge_pct; bVal = b.edge_pct; break
        case 'confidence': aVal = a.confidence; bVal = b.confidence; break
        case 'size': aVal = a.size_usd; bVal = b.size_usd; break
        default: return 0
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal
    })
  }, [signals, sortKey, sortDir])

  const handleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortIcon = ({ col }: { col: typeof sortKey }) => {
    if (sortKey !== col) return <ArrowUpDown className="w-2.5 h-2.5 text-neutral-600" />
    return sortDir === 'asc' ? <ArrowUp className="w-2.5 h-2.5 text-amber-500" /> : <ArrowDown className="w-2.5 h-2.5 text-amber-500" />
  }

  if (signals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-neutral-600">
        <Zap className="w-6 h-6 mb-2 opacity-30" />
        <p className="text-xs">No HFT signals yet</p>
        <p className="text-[10px] mt-0.5 text-neutral-700">Scanner running...</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[600px]">
        <thead className="sticky top-0 bg-[#0a0a0a] z-10">
          <tr className="text-neutral-600 text-left text-[10px] border-b border-neutral-800">
            <th className="py-1.5 px-2 font-medium w-16">Type</th>
            <th className="py-1.5 px-2 font-medium">Market</th>
            <th className="py-1.5 px-2 font-medium text-center w-10">Dir</th>
            <th
              className="py-1.5 px-2 font-medium text-right cursor-pointer hover:text-neutral-400"
              onClick={() => handleSort('latency')}
            >
              <div className="flex items-center justify-end gap-0.5">Lat <SortIcon col="latency" /></div>
            </th>
            <th className="py-1.5 px-2 font-medium text-right w-16">Bar</th>
            <th
              className="py-1.5 px-2 font-medium text-right cursor-pointer hover:text-neutral-400"
              onClick={() => handleSort('edge')}
            >
              <div className="flex items-center justify-end gap-0.5">Edge <SortIcon col="edge" /></div>
            </th>
            <th
              className="py-1.5 px-2 font-medium text-right cursor-pointer hover:text-neutral-400"
              onClick={() => handleSort('confidence')}
            >
              <div className="flex items-center justify-end gap-0.5">Conf <SortIcon col="confidence" /></div>
            </th>
            <th
              className="py-1.5 px-2 font-medium text-right cursor-pointer hover:text-neutral-400"
              onClick={() => handleSort('size')}
            >
              <div className="flex items-center justify-end gap-0.5">Size <SortIcon col="size" /></div>
            </th>
            <th className="py-1.5 px-2 font-medium text-center w-14">Status</th>
          </tr>
        </thead>
        <tbody>
          <AnimatePresence>
            {sorted.slice(0, maxRows).map((sig, i) => (
              <motion.tr
                key={sig.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ delay: i * 0.03 }}
                className="border-b border-neutral-800/40 hover:bg-neutral-800/20 text-[11px]"
              >
                <td className="py-1 px-2"><TypeBadge type={sig.type} /></td>
                <td className="py-1 px-2">
                  <span className="text-neutral-400 truncate block max-w-[120px]" title={sig.market}>{sig.market}</span>
                </td>
                <td className="py-1 px-2 text-center">
                  <span className={`text-[10px] font-semibold uppercase ${sig.direction === 'buy' ? 'text-green-500' : 'text-red-500'}`}>
                    {sig.direction}
                  </span>
                </td>
                <td className="py-1 px-2 text-right tabular-nums">
                  <span className={sig.latency_ms < 50 ? 'text-green-500' : sig.latency_ms < 100 ? 'text-yellow-500' : 'text-red-500'}>
                    {sig.latency_ms}ms
                  </span>
                </td>
                <td className="py-1 px-2"><LatencyBar ms={sig.latency_ms} /></td>
                <td className="py-1 px-2 text-right tabular-nums text-green-500">{sig.edge_pct.toFixed(1)}%</td>
                <td className="py-1 px-2 text-right tabular-nums text-blue-400">{(sig.confidence * 100).toFixed(0)}%</td>
                <td className="py-1 px-2 text-right tabular-nums text-amber-400">${sig.size_usd}</td>
                <td className="py-1 px-2 text-center"><StatusBadge status={sig.status} /></td>
              </motion.tr>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </div>
  )
}