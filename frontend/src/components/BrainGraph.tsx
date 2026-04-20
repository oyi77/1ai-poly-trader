import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useBrainGraph } from '../hooks/useBrainGraph'
import { Brain, TrendingUp, Zap, Target, Activity, AlertCircle } from 'lucide-react'

const nodeIcons: Record<string, any> = {
  signal: TrendingUp,
  ai: Brain,
  execution: Target,
  analysis: Activity,
}

const nodeColors: Record<string, { bg: string; border: string; text: string }> = {
  active: { bg: 'bg-green-500/20', border: 'border-green-500', text: 'text-green-400' },
  idle: { bg: 'bg-neutral-800', border: 'border-neutral-700', text: 'text-neutral-500' },
  processing: { bg: 'bg-yellow-500/20', border: 'border-yellow-500', text: 'text-yellow-400' },
  error: { bg: 'bg-red-500/20', border: 'border-red-500', text: 'text-red-400' },
}

const typeColors: Record<string, string> = {
  signal: '#3b82f6',
  ai: '#a855f7',
  execution: '#22c55e',
  analysis: '#f97316',
}

function CustomNode({ data }: { data: any }) {
  const Icon = nodeIcons[data.type] || Activity
  const colors = nodeColors[data.status] || nodeColors.idle

  return (
    <div className={`px-4 py-3 rounded-lg border-2 ${colors.bg} ${colors.border} min-w-[140px]`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${colors.text}`} />
        <div className={`text-xs font-bold uppercase tracking-wider ${colors.text}`}>
          {data.label}
        </div>
      </div>
      {data.status === 'processing' && (
        <div className="mt-2 h-1 bg-neutral-700 rounded-full overflow-hidden">
          <div className="h-full bg-yellow-500 animate-pulse" style={{ width: '60%' }} />
        </div>
      )}
    </div>
  )
}

const nodeTypes = {
  custom: CustomNode,
}

export default function BrainGraph() {
  const { graphData, transcript, status, loading } = useBrainGraph()
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  const initialNodes: Node[] = useMemo(() => [
    { id: 'mirofish', type: 'custom', position: { x: 400, y: 50 }, data: { label: 'MiroFish', type: 'ai', status: 'active' } },
    
    { id: 'btc_momentum', type: 'custom', position: { x: 100, y: 200 }, data: { label: 'BTC Momentum', type: 'signal', status: 'idle' } },
    { id: 'btc_oracle', type: 'custom', position: { x: 250, y: 200 }, data: { label: 'BTC Oracle', type: 'signal', status: 'idle' } },
    { id: 'weather_emos', type: 'custom', position: { x: 400, y: 200 }, data: { label: 'Weather EMOS', type: 'signal', status: 'idle' } },
    { id: 'copy_trader', type: 'custom', position: { x: 550, y: 200 }, data: { label: 'Copy Trader', type: 'signal', status: 'idle' } },
    { id: 'market_maker', type: 'custom', position: { x: 700, y: 200 }, data: { label: 'Market Maker', type: 'signal', status: 'idle' } },
    { id: 'kalshi_arb', type: 'custom', position: { x: 100, y: 320 }, data: { label: 'Kalshi Arb', type: 'signal', status: 'idle' } },
    { id: 'bond_scanner', type: 'custom', position: { x: 250, y: 320 }, data: { label: 'Bond Scanner', type: 'signal', status: 'idle' } },
    { id: 'whale_pnl', type: 'custom', position: { x: 400, y: 320 }, data: { label: 'Whale PNL', type: 'signal', status: 'idle' } },
    { id: 'realtime_scanner', type: 'custom', position: { x: 550, y: 320 }, data: { label: 'Realtime Scanner', type: 'signal', status: 'idle' } },
    
    { id: 'bull', type: 'custom', position: { x: 200, y: 450 }, data: { label: 'Bull Agent', type: 'ai', status: 'idle' } },
    { id: 'bear', type: 'custom', position: { x: 400, y: 450 }, data: { label: 'Bear Agent', type: 'ai', status: 'idle' } },
    { id: 'judge', type: 'custom', position: { x: 600, y: 450 }, data: { label: 'Judge Agent', type: 'ai', status: 'idle' } },
    
    { id: 'risk_manager', type: 'custom', position: { x: 300, y: 580 }, data: { label: 'Risk Manager', type: 'analysis', status: 'idle' } },
    { id: 'proposal_gen', type: 'custom', position: { x: 500, y: 580 }, data: { label: 'Proposal Gen', type: 'analysis', status: 'idle' } },
    
    { id: 'trade_executor', type: 'custom', position: { x: 300, y: 710 }, data: { label: 'Trade Executor', type: 'execution', status: 'idle' } },
    { id: 'trade_analyzer', type: 'custom', position: { x: 500, y: 710 }, data: { label: 'Trade Analyzer', type: 'analysis', status: 'idle' } },
  ], [])

  const initialEdges: Edge[] = useMemo(() => [
    { id: 'e-mirofish-btc_momentum', source: 'mirofish', target: 'btc_momentum', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-btc_oracle', source: 'mirofish', target: 'btc_oracle', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-weather_emos', source: 'mirofish', target: 'weather_emos', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-copy_trader', source: 'mirofish', target: 'copy_trader', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-market_maker', source: 'mirofish', target: 'market_maker', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-kalshi_arb', source: 'mirofish', target: 'kalshi_arb', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-bond_scanner', source: 'mirofish', target: 'bond_scanner', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-whale_pnl', source: 'mirofish', target: 'whale_pnl', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-mirofish-realtime_scanner', source: 'mirofish', target: 'realtime_scanner', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    
    { id: 'e-btc_momentum-bull', source: 'btc_momentum', target: 'bull', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-btc_oracle-bull', source: 'btc_oracle', target: 'bull', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-weather_emos-bull', source: 'weather_emos', target: 'bull', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-copy_trader-bear', source: 'copy_trader', target: 'bear', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-market_maker-bear', source: 'market_maker', target: 'bear', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-kalshi_arb-bear', source: 'kalshi_arb', target: 'bear', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-bond_scanner-judge', source: 'bond_scanner', target: 'judge', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-whale_pnl-judge', source: 'whale_pnl', target: 'judge', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-realtime_scanner-judge', source: 'realtime_scanner', target: 'judge', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    
    { id: 'e-bull-risk_manager', source: 'bull', target: 'risk_manager', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-bear-risk_manager', source: 'bear', target: 'risk_manager', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-judge-risk_manager', source: 'judge', target: 'risk_manager', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    
    { id: 'e-risk_manager-proposal_gen', source: 'risk_manager', target: 'proposal_gen', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    
    { id: 'e-proposal_gen-trade_executor', source: 'proposal_gen', target: 'trade_executor', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-trade_executor-trade_analyzer', source: 'trade_executor', target: 'trade_analyzer', animated: false, markerEnd: { type: MarkerType.ArrowClosed } },
  ], [])

  useEffect(() => {
    if (graphData?.nodes && graphData?.edges) {
      const updatedNodes = initialNodes.map(node => {
        const serverNode = graphData.nodes.find(n => n.id === node.id)
        if (serverNode) {
          return {
            ...node,
            data: {
              ...node.data,
              status: serverNode.status,
            },
          }
        }
        return node
      })
      setNodes(updatedNodes)

      const updatedEdges = initialEdges.map(edge => {
        const serverEdge = graphData.edges.find(e => e.id === edge.id)
        if (serverEdge) {
          return {
            ...edge,
            animated: serverEdge.animated,
            label: serverEdge.label,
          }
        }
        return edge
      })
      setEdges(updatedEdges)
    } else {
      setNodes(initialNodes)
      setEdges(initialEdges)
    }
  }, [graphData, initialNodes, initialEdges, setNodes, setEdges])

  if (loading) {
    return (
      <div className="h-full bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-10 h-10 mx-auto mb-4">
            <div className="absolute inset-0 border-2 border-neutral-800 rounded-full" />
            <div className="absolute inset-0 border-2 border-transparent border-t-green-500 rounded-full animate-spin" />
          </div>
          <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-mono">Loading Brain Graph</div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full bg-black flex">
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          className="bg-black"
          defaultEdgeOptions={{
            style: { stroke: '#525252', strokeWidth: 2 },
            animated: false,
          }}
        >
          <Background color="#262626" gap={16} />
          <Controls className="bg-neutral-900 border border-neutral-800" />
          <MiniMap
            nodeColor={(node) => {
              const type = node.data?.type || 'signal'
              return typeColors[type] || '#525252'
            }}
            className="bg-neutral-900 border border-neutral-800"
          />
        </ReactFlow>

        <div className="absolute top-4 left-4 bg-neutral-900 border border-neutral-800 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-green-500" />
            <span className="text-xs font-bold text-neutral-100 uppercase tracking-wider">Brain Status</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${status === 'open' ? 'bg-green-500' : 'bg-red-400'}`} />
            <span className={`text-[10px] font-mono ${status === 'open' ? 'text-neutral-400' : 'text-red-400'}`}>
              {status === 'open' ? 'Connected' : status === 'connecting' ? 'Connecting...' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      <div className="w-96 border-l border-neutral-800 bg-neutral-950 flex flex-col">
        <div className="shrink-0 border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-green-500" />
            <h2 className="text-sm font-bold text-neutral-100 uppercase tracking-wider">Debate Transcript</h2>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {transcript.length === 0 ? (
            <div className="text-center py-8">
              <AlertCircle className="w-8 h-8 text-neutral-700 mx-auto mb-2" />
              <p className="text-xs text-neutral-600">No active debate</p>
            </div>
          ) : (
            transcript.map((entry, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="bg-neutral-900 border border-neutral-800 rounded-lg p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-green-400 uppercase tracking-wider">{entry.speaker}</span>
                  <span className="text-[10px] text-neutral-600 font-mono">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-xs text-neutral-300 leading-relaxed">{entry.message}</p>
                {entry.vote && (
                  <div className="mt-2 pt-2 border-t border-neutral-800">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider ${
                        entry.vote === 'approve'
                          ? 'text-green-400'
                          : entry.vote === 'reject'
                          ? 'text-red-400'
                          : 'text-neutral-500'
                      }`}
                    >
                      Vote: {entry.vote}
                    </span>
                  </div>
                )}
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
