import { useState, lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { getAdminApiKey, setAdminApiKey } from '../api'

const SettingsEditor = lazy(() => import('../components/admin/SettingsEditor').then(m => ({ default: m.SettingsEditor })))
const SystemStatus = lazy(() => import('../components/admin/SystemStatus').then(m => ({ default: m.SystemStatus })))
const CopyTraderMonitor = lazy(() => import('../components/admin/CopyTraderMonitor').then(m => ({ default: m.CopyTraderMonitor })))
const Backtest = lazy(() => import('./Backtest').then(m => ({ default: m.Backtest })))
const StrategiesTab = lazy(() => import('../components/admin/StrategiesTab').then(m => ({ default: m.StrategiesTab })))
const MarketWatchTab = lazy(() => import('../components/admin/MarketWatchTab').then(m => ({ default: m.MarketWatchTab })))
const WalletConfigTab = lazy(() => import('../components/admin/WalletConfigTab').then(m => ({ default: m.WalletConfigTab })))
const CredentialsTab = lazy(() => import('../components/admin/CredentialsTab').then(m => ({ default: m.CredentialsTab })))
const TelegramTab = lazy(() => import('../components/admin/TelegramTab').then(m => ({ default: m.TelegramTab })))
const RiskTab = lazy(() => import('../components/admin/RiskTab').then(m => ({ default: m.RiskTab })))
const AITab = lazy(() => import('../components/admin/AITab').then(m => ({ default: m.AITab })))
const DebateMonitorTab = lazy(() => import('../components/admin/DebateMonitorTab').then(m => ({ default: m.DebateMonitorTab })))
const PendingApprovals = lazy(() => import('./PendingApprovals'))
const TradingTerminalTab = lazy(() => import('../components/dashboard/TradingTerminalTab').then(m => ({ default: m.TradingTerminalTab })))
const WhaleTrackerTab = lazy(() => import('../components/dashboard/WhaleTrackerTab').then(m => ({ default: m.WhaleTrackerTab })))
const EdgeTrackerTab = lazy(() => import('../components/dashboard/EdgeTrackerTab').then(m => ({ default: m.EdgeTrackerTab })))
const DecisionLogTab = lazy(() => import('../components/dashboard/DecisionLogTab').then(m => ({ default: m.DecisionLogTab })))
const SettlementsTab = lazy(() => import('../components/dashboard/SettlementsTab').then(m => ({ default: m.SettlementsTab })))

function AdminLoginGate({ login }: { login: (p: string) => Promise<void> }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password.trim()) return
    setLoading(true)
    setError('')
    try {
      await login(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-screen bg-black flex flex-col overflow-hidden font-mono">
      <div className="shrink-0 border-b border-neutral-800 px-4 py-2 flex items-center justify-between bg-black">
        <Link to="/" className="text-[10px] text-neutral-500 hover:text-green-500 uppercase tracking-wider transition-colors">PolyEdge</Link>
        <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-[0.2em]">Admin Dashboard</span>
        <span />
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="w-80 border border-neutral-800 bg-neutral-950 p-6">
          <div className="text-[9px] text-neutral-600 uppercase tracking-[0.3em] mb-5">Admin Access Required</div>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Admin password"
              autoFocus
              className="w-full bg-black border border-neutral-800 text-neutral-200 text-xs px-3 py-2 focus:outline-none focus:border-green-500/40 font-mono placeholder-neutral-700"
            />
            {error && <p className="text-[10px] text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading || !password.trim()}
              className="px-3 py-1.5 bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] uppercase tracking-wider hover:bg-green-500/20 transition-colors disabled:opacity-40"
            >
              {loading ? 'Verifying...' : 'Login'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

const TABS = ['System', 'Settings', 'Trading Terminal', 'Whale Tracker', 'Edge Tracker', 'Decision Log', 'Settlements', 'Backtest', 'Risk', 'Credentials', 'Strategies', 'Copy Trader', 'Telegram', 'Market Watch', 'Wallet Config', 'AI', 'Debate Monitor', 'Pending Approvals'] as const
type Tab = typeof TABS[number]

function ApiKeyBar() {
  const [key, setKey] = useState(getAdminApiKey())
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    setAdminApiKey(key)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="shrink-0 bg-neutral-950 border-b border-neutral-800 px-4 py-1.5 flex items-center gap-3">
      <span className="text-[9px] text-neutral-600 uppercase tracking-wider shrink-0">Admin Key</span>
      <input
        type="password"
        value={key}
        onChange={e => setKey(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && handleSave()}
        placeholder="Bearer token (leave blank if not required)"
        className="flex-1 bg-transparent border border-neutral-800 text-neutral-400 text-[10px] px-2 py-0.5 font-mono focus:border-neutral-600 focus:outline-none"
      />
      <button
        onClick={handleSave}
        className="px-2 py-0.5 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[9px] uppercase tracking-wider hover:border-neutral-600 transition-colors"
      >
        {saved ? 'Saved' : 'Set'}
      </button>
    </div>
  )
}

export default function Admin() {
  const [activeTab, setActiveTab] = useState<Tab>('System')
  const { isAuthenticated, authRequired, login, logout } = useAuth()

  if (authRequired && !isAuthenticated) {
    return <AdminLoginGate login={login} />
  }

  return (
    <div className="h-screen bg-black text-neutral-200 flex flex-col overflow-hidden font-mono">
      <div className="shrink-0 border-b border-neutral-800 px-4 py-2 flex items-center justify-between bg-black">
        <Link to="/" className="text-[10px] text-neutral-500 hover:text-green-500 uppercase tracking-wider transition-colors">PolyEdge</Link>
        <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-[0.2em]">Admin Dashboard</span>
        {authRequired ? (
          <button onClick={logout} className="text-[9px] text-neutral-600 hover:text-neutral-400 uppercase tracking-wider transition-colors">Logout</button>
        ) : (
          <span />
        )}
      </div>
      {!authRequired && <ApiKeyBar />}

      {/* Tab Bar */}
      <div className="shrink-0 border-b border-neutral-800 px-4 flex items-center gap-0">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-[10px] uppercase tracking-wider border-b-2 transition-colors ${
              activeTab === tab
                ? 'text-green-500 border-green-500'
                : 'text-neutral-500 border-transparent hover:text-neutral-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 max-w-100vw">
        {activeTab === 'System' && <SystemStatus />}
        {activeTab === 'Settings' && <SettingsEditor />}
        {activeTab === 'Trading Terminal' && <TradingTerminalTab />}
        {activeTab === 'Whale Tracker' && <WhaleTrackerTab />}
        {activeTab === 'Edge Tracker' && <EdgeTrackerTab />}
        {activeTab === 'Decision Log' && <DecisionLogTab />}
        {activeTab === 'Settlements' && <SettlementsTab />}
        {activeTab === 'Backtest' && <Backtest />}
        {activeTab === 'Risk' && <RiskTab />}
        {activeTab === 'Credentials' && <CredentialsTab />}
        {activeTab === 'Strategies' && <StrategiesTab />}
        {activeTab === 'Copy Trader' && <CopyTraderMonitor />}
        {activeTab === 'Telegram' && <TelegramTab />}
        {activeTab === 'Market Watch' && <MarketWatchTab />}
        {activeTab === 'Wallet Config' && <WalletConfigTab />}
        {activeTab === 'AI' && <AITab />}
        {activeTab === 'Debate Monitor' && <DebateMonitorTab />}
        {activeTab === 'Pending Approvals' && <PendingApprovals />}
      </div>
    </div>
  )
}
