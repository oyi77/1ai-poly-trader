import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { 
  Zap, Brain, Activity, Radio, ChevronRight, 
  Signal, Shield, DollarSign, AlertTriangle, 
  TrendingUp, TrendingDown, Mic, Play, Pause
} from 'lucide-react'

interface DecisionCard {
  id: string
  signal: string
  timestamp: Date
  stage: 'detected' | 'analyzing' | 'debate' | 'judge' | 'risk' | 'executed' | 'blocked'
  bullReason?: string
  bearReason?: string
  verdict?: 'bull' | 'bear' | null
  riskScore?: number
  decision?: 'executed' | 'blocked'
}

interface StrategyPulse {
  name: string
  status: 'thinking' | 'fired' | 'idle'
  lastPulse: number
}

function LiveStream() {
  const [activeTab, setActiveTab] = useState<'all' | 'pipeline' | 'arena' | 'pulse'>('all')
  const [isLive, setIsLive] = useState(true)

  return (
    <div className="h-full bg-black overflow-hidden flex flex-col">
      <LiveStreamHeader activeTab={activeTab} setActiveTab={setActiveTab} isLive={isLive} setIsLive={setIsLive} />
      
      <div className="flex-1 overflow-hidden">
        {activeTab === 'all' ? (
          <div className="h-full grid grid-cols-1 lg:grid-cols-2 grid-rows-2 gap-2 p-2">
            <div className="lg:row-span-2 bg-neutral-900 rounded-lg overflow-hidden">
              <PipelineView isLive={isLive} />
            </div>
            <div className="bg-neutral-900 rounded-lg overflow-hidden">
              <ArenaView isLive={isLive} />
            </div>
            <div className="bg-neutral-900 rounded-lg overflow-hidden">
              <PulseView isLive={isLive} />
            </div>
          </div>
        ) : activeTab === 'pipeline' ? (
          <PipelineView isLive={isLive} fullPage />
        ) : activeTab === 'arena' ? (
          <ArenaView isLive={isLive} fullPage />
        ) : (
          <PulseView isLive={isLive} fullPage />
        )}
      </div>
    </div>
  )
}

function LiveStreamHeader({ activeTab, setActiveTab, isLive, setIsLive }: {
  activeTab: 'all' | 'pipeline' | 'arena' | 'pulse'
  setActiveTab: (t: 'all' | 'pipeline' | 'arena' | 'pulse') => void
  isLive: boolean
  setIsLive: (v: boolean) => void
}) {
  const tabs = [
    { id: 'all', label: 'All Three', icon: Grid3X3 },
    { id: 'pipeline', label: 'Pipeline', icon: Kanban },
    { id: 'arena', label: 'Arena', icon: Mic },
    { id: 'pulse', label: 'Pulse', icon: Activity },
  ] as const

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-neutral-800 bg-neutral-900/80">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Radio className={`w-4 h-4 ${isLive ? 'text-green-500 animate-pulse' : 'text-neutral-500'}`} />
          <span className="text-sm font-bold text-neutral-100 uppercase tracking-wider">Live Stream</span>
        </div>
        
        <div className="flex gap-1 ml-4">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 text-xs uppercase tracking-wider rounded transition-colors ${
                activeTab === tab.id 
                  ? 'bg-green-500/20 text-green-400 border border-green-500/40' 
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={() => setIsLive(!isLive)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded border transition-colors ${
          isLive 
            ? 'bg-red-500/20 border-red-500/40 text-red-400' 
            : 'bg-neutral-800 border-neutral-700 text-neutral-400'
        }`}
      >
        {isLive ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        <span className="text-xs uppercase tracking-wider">{isLive ? 'Pause' : 'Play'}</span>
      </button>
    </div>
  )
}

function Grid3X3({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="1" width="5" height="5" rx="1" />
      <rect x="6" y="1" width="9" height="5" rx="1" />
      <rect x="1" y="6" width="5" height="9" rx="1" />
      <rect x="6" y="6" width="9" height="9" rx="1" />
    </svg>
  )
}

function Kanban({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="2" width="4" height="12" rx="1" />
      <rect x="6" y="2" width="4" height="12" rx="1" />
      <rect x="11" y="2" width="4" height="12" rx="1" />
    </svg>
  )
}

function PipelineView({ isLive, fullPage = false }: { isLive: boolean; fullPage?: boolean }) {
  const [cards, setCards] = useState<DecisionCard[]>([
    { id: '1', signal: 'BTC > $95K by Friday', timestamp: new Date(), stage: 'debate', bullReason: 'Whale accumulation detected', bearReason: 'Overbought RSI at 78' },
    { id: '2', signal: 'ETH > $2.5K this week', timestamp: new Date(Date.now() - 60000), stage: 'judge', verdict: 'bull' },
    { id: '3', signal: 'SOL > $180 by weekend', timestamp: new Date(Date.now() - 120000), stage: 'executed', decision: 'executed', verdict: 'bull', riskScore: 0.65 },
    { id: '4', signal: 'AVAX < $35 by Monday', timestamp: new Date(Date.now() - 180000), stage: 'blocked', decision: 'blocked', verdict: 'bear', riskScore: 0.92 },
  ])

  const stages = ['detected', 'analyzing', 'debate', 'judge', 'risk', 'executed', 'blocked'] as const

  useEffect(() => {
    if (!isLive) return
    
    const interval = setInterval(() => {
      const randomStage = stages[Math.floor(Math.random() * (stages.length - 2))]
      const newCard: DecisionCard = {
        id: Date.now().toString(),
        signal: ['BTC > $100K', 'ETH > $3K', 'SOL > $200', 'DOGE > $0.50'][Math.floor(Math.random() * 4)],
        timestamp: new Date(),
        stage: randomStage,
      }
      
      setCards(prev => [...prev.slice(-10), newCard])
    }, 4000)
    
    return () => clearInterval(interval)
  }, [isLive])

  const stageLabels: Record<string, { label: string; icon: any; color: string }> = {
    detected: { label: 'Signal Detected', icon: Signal, color: 'text-blue-400' },
    analyzing: { label: 'AI Analyzing', icon: Brain, color: 'text-purple-400' },
    debate: { label: 'Bull vs Bear', icon: Zap, color: 'text-yellow-400' },
    judge: { label: 'Judge Decision', icon: TrendingUp, color: 'text-orange-400' },
    risk: { label: 'Risk Check', icon: Shield, color: 'text-cyan-400' },
    executed: { label: 'Trade Executed', icon: DollarSign, color: 'text-green-400' },
    blocked: { label: 'Blocked', icon: AlertTriangle, color: 'text-red-400' },
  }

  const getCardsForStage = (stage: string) => cards.filter(c => c.stage === stage)

  return (
    <div className={`h-full flex flex-col ${fullPage ? 'p-4' : 'p-2'}`}>
      <div className="flex items-center gap-2 mb-3 px-2">
        <Kanban className="w-4 h-4 text-green-500" />
        <span className="text-xs font-bold text-neutral-100 uppercase tracking-wider">Decision Pipeline</span>
        <span className="text-[10px] text-neutral-500 ml-auto">Real-time signal flow</span>
      </div>

      <div className="flex-1 flex gap-2 overflow-x-auto pb-2">
        {stages.map((stage, i) => {
          const stageCards = getCardsForStage(stage)
          const info = stageLabels[stage]
          const Icon = info.icon
          
          return (
            <div key={stage} className="flex-shrink-0 w-28 flex flex-col">
              <div className={`flex items-center gap-1.5 mb-2 px-1 ${info.color}`}>
                <Icon className="w-3 h-3" />
                <span className="text-[10px] font-bold uppercase tracking-wider truncate">{info.label}</span>
              </div>
              
              <div className="flex-1 space-y-1.5 overflow-y-auto min-h-0">
                {stageCards.map(card => (
                  <motion.div
                    key={card.id}
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="bg-neutral-800 border border-neutral-700 rounded p-2 cursor-pointer hover:border-green-500/40 transition-colors"
                  >
                    <div className="text-[9px] text-neutral-200 font-medium truncate">{card.signal}</div>
                    <div className="text-[8px] text-neutral-500 mt-1">
                      {card.timestamp.toLocaleTimeString()}
                    </div>
                    {card.verdict && (
                      <div className={`text-[8px] mt-1 font-bold ${card.verdict === 'bull' ? 'text-green-400' : 'text-red-400'}`}>
                        {card.verdict.toUpperCase()}
                      </div>
                    )}
                    {card.riskScore !== undefined && (
                      <div className="text-[8px] text-neutral-400 mt-1">
                        Risk: {(card.riskScore * 100).toFixed(0)}%
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>

              {i < stages.length - 1 && (
                <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-full">
                  <ChevronRight className="w-3 h-3 text-neutral-600" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ArenaView({ isLive, fullPage = false }: { isLive: boolean; fullPage?: boolean }) {
  const [bullText, setBullText] = useState('')
  const [bearText, setBearText] = useState('')
  const [verdict, setVerdict] = useState<'bull' | 'bear' | null>(null)
  const [isDebating, setIsDebating] = useState(true)
  
  const bullArguments = [
    "Whale wallets accumulating +$2.3M in last 24h...",
    "On-chain metrics show strong accumulation pattern...",
    "Funding rates still positive, market sentiment bullish...",
    "Volume surge 340% above 30-day average...",
    "RSI divergence suggests upward momentum intact...",
  ]
  
  const bearArguments = [
    "Exchange reserves increasing - potential sell pressure...",
    "Overbought on 4H chart, RSI at 78...",
    "Whale distribution detected, smart money exiting...",
    "Volume decreasing while price still rising - divergence...",
    "Multiple resistance levels overhead at $96K...",
  ]

  useEffect(() => {
    if (!isLive || !isDebating) return
    
    let bullIndex = 0
    let bearIndex = 0
    
    const bullInterval = setInterval(() => {
      if (bullIndex < bullArguments.length) {
        setBullText(prev => prev + (prev ? '\n' : '') + bullArguments[bullIndex])
        bullIndex++
      }
    }, 1500)
    
    const bearInterval = setInterval(() => {
      if (bearIndex < bearArguments.length) {
        setBearText(prev => prev + (prev ? '\n' : '') + bearArguments[bearIndex])
        bearIndex++
      }
    }, 1800)

    const verdictTimeout = setTimeout(() => {
      setVerdict(Math.random() > 0.5 ? 'bull' : 'bear')
      setIsDebating(false)
    }, 12000)

    return () => {
      clearInterval(bullInterval)
      clearInterval(bearInterval)
      clearTimeout(verdictTimeout)
    }
  }, [isLive])

  const resetDebate = () => {
    setBullText('')
    setBearText('')
    setVerdict(null)
    setIsDebating(true)
  }

  return (
    <div className={`h-full flex flex-col ${fullPage ? 'p-4' : 'p-2'}`}>
      <div className="flex items-center gap-2 mb-3 px-2">
        <Mic className="w-4 h-4 text-yellow-500" />
        <span className="text-xs font-bold text-neutral-100 uppercase tracking-wider">AI Arena - Live Debate</span>
        <button onClick={resetDebate} className="ml-auto text-[10px] text-neutral-500 hover:text-neutral-300">
          New Debate
        </button>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-2">
        <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-2 flex flex-col">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingUp className="w-3 h-3 text-green-400" />
            <span className="text-[10px] font-bold text-green-400 uppercase">Bull Case</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            <p className="text-[10px] text-green-300/80 font-mono leading-relaxed whitespace-pre-line">
              {bullText}
              {isDebating && <span className="animate-pulse">▊</span>}
            </p>
          </div>
        </div>

        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-2 flex flex-col">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingDown className="w-3 h-3 text-red-400" />
            <span className="text-[10px] font-bold text-red-400 uppercase">Bear Case</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            <p className="text-[10px] text-red-300/80 font-mono leading-relaxed whitespace-pre-line">
              {bearText}
              {isDebating && <span className="animate-pulse">▊</span>}
            </p>
          </div>
        </div>
      </div>

      {verdict && (
        <motion.div 
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className={`mt-2 p-2 rounded-lg border text-center ${
            verdict === 'bull' 
              ? 'bg-green-500/20 border-green-500/40' 
              : 'bg-red-500/20 border-red-500/40'
          }`}
        >
          <div className={`text-xs font-bold uppercase tracking-wider ${
            verdict === 'bull' ? 'text-green-400' : 'text-red-400'
          }`}>
            Judge Verdict: {verdict === 'bull' ? '🟢 BULL' : '🔴 BEAR'}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function PulseView({ isLive, fullPage = false }: { isLive: boolean; fullPage?: boolean }) {
  const [strategies, setStrategies] = useState<StrategyPulse[]>([
    { name: 'BTC Momentum', status: 'thinking', lastPulse: Date.now() },
    { name: 'Weather EMOS', status: 'fired', lastPulse: Date.now() - 5000 },
    { name: 'Whale Tracker', status: 'idle', lastPulse: Date.now() - 30000 },
    { name: 'Arb Scanner', status: 'thinking', lastPulse: Date.now() },
    { name: 'Copy Trader', status: 'idle', lastPulse: Date.now() - 60000 },
    { name: 'MiroFish', status: 'thinking', lastPulse: Date.now() },
  ])

  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!isLive) return

    const interval = setInterval(() => {
      setStrategies(prev => prev.map(s => ({
        ...s,
        status: Math.random() > 0.7 
          ? (s.status === 'idle' ? 'thinking' : s.status)
          : s.status === 'thinking' ? 'fired' : s.status === 'fired' ? 'idle' : s.status,
        lastPulse: Date.now()
      })))
    }, 2000)

    return () => clearInterval(interval)
  }, [isLive])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    let animationId: number
    let phase = 0

    const draw = () => {
      const { width, height } = canvas
      ctx.fillStyle = '#0a0a0a'
      ctx.fillRect(0, 0, width, height)
      
      const activeStrategies = strategies.filter(s => s.status === 'thinking' || s.status === 'fired')
      
      activeStrategies.forEach((strategy, i) => {
        const y = 30 + i * 25
        const color = strategy.status === 'fired' ? '#22c55e' : strategy.status === 'thinking' ? '#a855f7' : '#6b7280'
        
        ctx.strokeStyle = color
        ctx.lineWidth = 2
        ctx.beginPath()
        
        for (let x = 0; x < width; x++) {
          const wave = Math.sin((x / 20) + phase + (strategy.status === 'fired' ? 0 : Math.PI))
          const amplitude = strategy.status === 'fired' ? 8 : strategy.status === 'thinking' ? 4 : 0
          const yOffset = wave * amplitude
          
          if (x === 0) {
            ctx.moveTo(x, y + yOffset)
          } else {
            ctx.lineTo(x, y + yOffset)
          }
        }
        
        ctx.stroke()
        
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(width - 20, y, 4, 0, Math.PI * 2)
        ctx.fill()
        
        ctx.fillStyle = '#9ca3af'
        ctx.font = '9px monospace'
        ctx.fillText(strategy.name, 10, y + 3)
      })
      
      phase += 0.1
      animationId = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(animationId)
  }, [strategies, isLive])

  return (
    <div className={`h-full flex flex-col ${fullPage ? 'p-4' : 'p-2'}`}>
      <div className="flex items-center gap-2 mb-3 px-2">
        <Activity className="w-4 h-4 text-purple-500" />
        <span className="text-xs font-bold text-neutral-100 uppercase tracking-wider">Neural Pulse</span>
        <span className="text-[10px] text-neutral-500">EKG heartbeat monitor</span>
      </div>

      <div className="flex-1 relative">
        <canvas 
          ref={canvasRef}
          className="absolute inset-0 w-full h-full"
          width={400}
          height={200}
        />
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2">
        {strategies.slice(0, 6).map(s => (
          <div key={s.name} className="bg-neutral-800/50 rounded px-2 py-1 flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${
              s.status === 'thinking' ? 'bg-purple-500 animate-pulse' :
              s.status === 'fired' ? 'bg-green-500' : 'bg-neutral-600'
            }`} />
            <span className="text-[9px] text-neutral-400 truncate">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default LiveStream