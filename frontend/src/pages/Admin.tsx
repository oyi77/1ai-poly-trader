import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { NavBar } from '../components/NavBar'
import { SettingsEditor } from '../components/admin/SettingsEditor'
import { SystemStatus } from '../components/admin/SystemStatus'
import { CopyTraderMonitor } from '../components/admin/CopyTraderMonitor'
import { Backtest } from './Backtest'
import { useAuth } from '../hooks/useAuth'
import {
  getAdminApiKey,
  setAdminApiKey,
  updateCredentials,
  changeAdminPassword,
  fetchStrategies,
  updateStrategy,
  runStrategyNow,
  fetchMarketWatches,
  createMarketWatch,
  deleteMarketWatch,
  fetchWalletConfigs,
  createWalletConfig,
  updateWalletConfig,
  deleteWalletConfig,
  fetchSystemStatus,
  switchTradingMode,
  fetchAdminSettings,
  updateAdminSettings,
  fetchAISuggest,
} from '../api'

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
      <NavBar title="Admin Dashboard" />
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

const TABS = ['System', 'Backtest', 'Risk', 'Credentials', 'Strategies', 'Settings', 'Copy Trader', 'Telegram', 'Market Watch', 'Wallet Config', 'AI'] as const
type Tab = typeof TABS[number]

function StrategiesTab() {
  const qc = useQueryClient()
  const [runState, setRunState] = useState<Record<string, 'idle' | 'running' | 'done'>>({})

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    refetchInterval: 30_000,
  })

  const handleToggle = async (name: string, enabled: boolean) => {
    await updateStrategy(name, { enabled: !enabled })
    qc.invalidateQueries({ queryKey: ['strategies'] })
  }

  const handleRunNow = async (name: string) => {
    setRunState(s => ({ ...s, [name]: 'running' }))
    try {
      await runStrategyNow(name)
      setRunState(s => ({ ...s, [name]: 'done' }))
      setTimeout(() => setRunState(s => ({ ...s, [name]: 'idle' })), 2000)
    } catch {
      setRunState(s => ({ ...s, [name]: 'idle' }))
    }
  }

  if (isLoading) return <div className="text-[10px] text-neutral-600">Loading strategies...</div>

  return (
    <div className="space-y-2">
      <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">
        Strategies — {strategies.length} total
      </div>
      {strategies.map(s => (
        <div key={s.name} className="border border-neutral-800 p-3 space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-neutral-200 font-mono">{s.name}</span>
              <span className="text-[9px] text-neutral-600 uppercase tracking-wider">{s.category}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleRunNow(s.name)}
                disabled={runState[s.name] === 'running'}
                className="px-2 py-0.5 border border-neutral-700 text-neutral-400 text-[9px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
              >
                {runState[s.name] === 'running' ? 'Running...' : runState[s.name] === 'done' ? 'Done' : 'Run Now'}
              </button>
              <button
                onClick={() => handleToggle(s.name, s.enabled)}
                className={`px-2 py-0.5 border text-[9px] uppercase tracking-wider transition-colors ${
                  s.enabled
                    ? 'border-green-700 text-green-500 hover:border-green-500'
                    : 'border-neutral-700 text-neutral-500 hover:border-neutral-500'
                }`}
              >
                {s.enabled ? 'Enabled' : 'Disabled'}
              </button>
            </div>
          </div>
          <div className="text-[10px] text-neutral-500">{s.description}</div>
          <div className="text-[9px] text-neutral-600 font-mono">interval: {s.interval_seconds}s</div>
        </div>
      ))}
    </div>
  )
}

function MarketWatchTab() {
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

function WalletConfigTab() {
  const qc = useQueryClient()
  const [address, setAddress] = useState('')
  const [pseudonym, setPseudonym] = useState('')
  const [adding, setAdding] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['wallet-configs'],
    queryFn: () => fetchWalletConfigs(),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleToggle = async (id: number, enabled: boolean) => {
    await updateWalletConfig(id, { enabled: !enabled })
    qc.invalidateQueries({ queryKey: ['wallet-configs'] })
  }

  const handleDelete = async (id: number) => {
    await deleteWalletConfig(id)
    qc.invalidateQueries({ queryKey: ['wallet-configs'] })
  }

  const handleTrack = async () => {
    if (!address.trim()) return
    setAdding(true)
    try {
      await createWalletConfig({ address: address.trim(), pseudonym: pseudonym.trim() || undefined })
      setAddress('')
      setPseudonym('')
      qc.invalidateQueries({ queryKey: ['wallet-configs'] })
    } finally {
      setAdding(false)
    }
  }

  const truncate = (addr: string) =>
    addr.length > 16 ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : addr

  if (isLoading) return <div className="text-[10px] text-neutral-600">Loading wallet configs...</div>

  return (
    <div className="space-y-4">
      <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
        Wallet Config — {total} total
      </div>
      <div className="border border-neutral-800">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="border-b border-neutral-800">
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Address</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Pseudonym</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Source</th>
              <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Enabled</th>
              <th className="px-3 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {items.map(row => (
              <tr key={row.id} className="border-b border-neutral-800/50 hover:bg-neutral-900/30">
                <td className="px-3 py-1.5 text-neutral-300" title={row.address}>{truncate(row.address)}</td>
                <td className="px-3 py-1.5 text-neutral-400">{row.pseudonym || '—'}</td>
                <td className="px-3 py-1.5 text-neutral-500">{row.source || '—'}</td>
                <td className="px-3 py-1.5">
                  <button
                    onClick={() => handleToggle(row.id, row.enabled)}
                    className={`text-[9px] uppercase tracking-wider transition-colors ${
                      row.enabled ? 'text-green-500 hover:text-green-400' : 'text-neutral-600 hover:text-neutral-400'
                    }`}
                  >
                    {row.enabled ? 'yes' : 'no'}
                  </button>
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
                <td colSpan={5} className="px-3 py-3 text-neutral-700 text-center">No wallets configured</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="border border-neutral-800 p-3">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-2">Track Wallet</div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={address}
            onChange={e => setAddress(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleTrack()}
            placeholder="0x address"
            className="bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none w-64 placeholder:text-neutral-700"
          />
          <input
            type="text"
            value={pseudonym}
            onChange={e => setPseudonym(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleTrack()}
            placeholder="Pseudonym (optional)"
            className="bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none w-48 placeholder:text-neutral-700"
          />
          <button
            onClick={handleTrack}
            disabled={adding || !address.trim()}
            className="px-3 py-1 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
          >
            {adding ? 'Tracking...' : 'Track'}
          </button>
        </div>
      </div>
    </div>
  )
}

const MODE_META = {
  paper:   { label: 'Paper',   color: 'text-amber-400',  border: 'border-amber-500/30',  desc: 'Simulated orders, no credentials needed' },
  testnet: { label: 'Testnet', color: 'text-yellow-400', border: 'border-yellow-500/30', desc: 'Real orders on Amoy testnet (chain 80002)' },
  live:    { label: 'Live',    color: 'text-red-400',    border: 'border-red-500/30',    desc: 'Real money on Polygon mainnet' },
} as const

function CredentialsTab() {
  const qc = useQueryClient()
  const [privateKey, setPrivateKey] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [apiPassphrase, setApiPassphrase] = useState('')
  const [saveStatus, setSaveStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [switchingMode, setSwitchingMode] = useState(false)

  const { data: sysStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['admin-system-creds'],
    queryFn: fetchSystemStatus,
    refetchInterval: 15_000,
  })

  const handleSave = async () => {
    const payload: Record<string, string> = {}
    if (privateKey.trim()) payload.private_key = privateKey.trim()
    if (apiKey.trim()) payload.api_key = apiKey.trim()
    if (apiSecret.trim()) payload.api_secret = apiSecret.trim()
    if (apiPassphrase.trim()) payload.api_passphrase = apiPassphrase.trim()
    if (!Object.keys(payload).length) return

    setSaving(true)
    setSaveStatus(null)
    try {
      const result = await updateCredentials(payload)
      setSaveStatus({ ok: true, message: `Saved: ${result.updated.map(k => k.replace('POLYMARKET_', '')).join(', ')}` })
      setPrivateKey('')
      setApiKey('')
      setApiSecret('')
      setApiPassphrase('')
      refetchStatus()
      qc.invalidateQueries({ queryKey: ['admin-system'] })
    } catch {
      setSaveStatus({ ok: false, message: 'Failed to save credentials' })
    } finally {
      setSaving(false)
    }
  }

  const handleSwitchMode = async (mode: 'paper' | 'testnet' | 'live') => {
    setSwitchingMode(true)
    try {
      await switchTradingMode(mode)
      refetchStatus()
      qc.invalidateQueries({ queryKey: ['admin-system'] })
    } finally {
      setSwitchingMode(false)
    }
  }

  const fields = [
    { label: 'Private Key',    hint: '0x hex — required for testnet + live', value: privateKey,    setter: setPrivateKey,    badge: 'testnet + live' },
    { label: 'API Key',        hint: 'CLOB API key — required for live only', value: apiKey,        setter: setApiKey,        badge: 'live' },
    { label: 'API Secret',     hint: 'CLOB API secret',                       value: apiSecret,     setter: setApiSecret,     badge: 'live' },
    { label: 'API Passphrase', hint: 'CLOB API passphrase',                   value: apiPassphrase, setter: setApiPassphrase, badge: 'live' },
  ]

  const currentMode = sysStatus?.trading_mode ?? 'paper'
  const credsReady = {
    paper:   true,
    testnet: sysStatus?.creds_testnet ?? false,
    live:    sysStatus?.creds_live ?? false,
  }
  const missing = {
    testnet: sysStatus?.missing_for_testnet ?? [],
    live:    sysStatus?.missing_for_live ?? [],
  }

  return (
    <div className="space-y-4">
      {/* Mode Switcher */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Trading Mode</div>
        <div className="grid grid-cols-3 gap-2 mb-3">
          {(['paper', 'testnet', 'live'] as const).map(mode => {
            const meta = MODE_META[mode]
            const ready = credsReady[mode]
            const active = currentMode === mode
            const miss = mode !== 'paper' ? missing[mode] : []
            return (
              <button
                key={mode}
                disabled={switchingMode || active}
                onClick={() => handleSwitchMode(mode)}
                title={miss.length > 0 ? `Missing: ${miss.join(', ')}` : meta.desc}
                className={`relative p-3 border text-left transition-colors disabled:cursor-not-allowed ${
                  active
                    ? `${meta.border} bg-neutral-900`
                    : 'border-neutral-800 hover:border-neutral-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${active ? meta.color : 'text-neutral-500'}`}>
                    {meta.label}
                  </span>
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${ready ? 'bg-green-500' : 'bg-neutral-700'}`} />
                </div>
                <div className="text-[9px] text-neutral-600 leading-tight">{meta.desc}</div>
                {miss.length > 0 && (
                  <div className="text-[8px] text-amber-600/80 mt-1 truncate">
                    Need: {miss.map(k => k.replace('POLYMARKET_', '')).join(', ')}
                  </div>
                )}
                {active && (
                  <div className={`absolute top-1.5 right-1.5 text-[8px] uppercase tracking-wider ${meta.color}`}>active</div>
                )}
              </button>
            )
          })}
        </div>
        {switchingMode && <div className="text-[10px] text-neutral-500">Switching mode...</div>}
      </div>

      {/* Credential form */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Polymarket Credentials</div>
        <p className="text-[11px] text-neutral-600 mb-4 leading-relaxed">
          Persisted to <span className="text-neutral-400 font-mono">.env</span> and hot-reloaded — no restart needed.
          Only fill fields you want to update.
        </p>
        <div className="space-y-3">
          {fields.map(({ label, hint, value, setter, badge }) => (
            <div key={label}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] text-neutral-400 uppercase tracking-wider w-36">{label}</span>
                <span className="text-[9px] text-neutral-600">({badge})</span>
              </div>
              <input
                type="password"
                value={value}
                onChange={e => setter(e.target.value)}
                placeholder={hint}
                className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
              />
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save Credentials'}
          </button>
          {saveStatus && (
            <span className={`text-[10px] font-mono ${saveStatus.ok ? 'text-green-500' : 'text-red-500'}`}>
              {saveStatus.message}
            </span>
          )}
        </div>
      </div>

      <AdminPasswordSection />
    </div>
  )
}

function AdminPasswordSection() {
  const { authRequired, logout } = useAuth()
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null)

  if (!authRequired) return null

  const handleSave = async () => {
    if (!newPw.trim()) return
    if (newPw !== confirmPw) {
      setStatus({ ok: false, message: 'Passwords do not match' })
      return
    }
    setSaving(true)
    setStatus(null)
    try {
      const result = await changeAdminPassword(newPw)
      setStatus({ ok: true, message: result.message })
      setNewPw('')
      setConfirmPw('')
      setTimeout(() => logout(), 1500)
    } catch {
      setStatus({ ok: false, message: 'Failed to change password' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border border-neutral-800 bg-neutral-900/20 p-4">
      <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Change Admin Password</div>
      <p className="text-[11px] text-neutral-600 mb-4 leading-relaxed">
        Updates <span className="text-neutral-400 font-mono">ADMIN_API_KEY</span> in <span className="text-neutral-400 font-mono">.env</span>. You will be logged out after saving.
      </p>
      <div className="space-y-3">
        <input
          type="password"
          value={newPw}
          onChange={e => setNewPw(e.target.value)}
          placeholder="New password"
          className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
        />
        <input
          type="password"
          value={confirmPw}
          onChange={e => setConfirmPw(e.target.value)}
          placeholder="Confirm new password"
          className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
        />
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !newPw.trim() || !confirmPw.trim()}
          className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
        >
          {saving ? 'Saving...' : 'Change Password'}
        </button>
        {status && (
          <span className={`text-[10px] font-mono ${status.ok ? 'text-green-500' : 'text-red-500'}`}>
            {status.message}
          </span>
        )}
      </div>
    </div>
  )
}

function TelegramTab() {
  return (
    <div className="space-y-4">
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Telegram Bot</div>
        <p className="text-[11px] text-neutral-400 leading-relaxed">
          Configure Telegram bot token and admin chat IDs in the Settings tab under the Telegram section.
          The bot sends trade notifications, signal alerts, and system status updates to configured admin chats.
        </p>
      </div>
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Test Message</div>
        <p className="text-[11px] text-neutral-600 mb-3">
          Send a test message to verify bot configuration. Requires TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_IDS to be set.
        </p>
        <button
          className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[10px] uppercase tracking-wider hover:border-neutral-600 transition-colors"
          onClick={() => {
            fetch(`${import.meta.env.VITE_API_URL || ''}/api/admin/alerts/test`, { method: 'POST' })
              .catch(() => {})
          }}
        >
          Send Test Message
        </button>
      </div>
    </div>
  )
}

function RiskTab() {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null)

  const RISK_FIELDS = [
    { key: 'INITIAL_BANKROLL',          label: 'Initial Bankroll ($)',         hint: 'Starting capital (used on reset)',       type: 'number', section: 'Capital' },
    { key: 'DAILY_LOSS_LIMIT',          label: 'Daily Loss Limit ($)',         hint: 'Stop trading if daily PNL drops below', type: 'number', section: 'Capital' },
    { key: 'MAX_TRADE_SIZE',            label: 'Max Trade Size ($)',           hint: 'Single trade cap in USDC',              type: 'number', section: 'BTC' },
    { key: 'MIN_EDGE_THRESHOLD',        label: 'Min Edge Threshold',           hint: 'e.g. 0.02 = 2% edge required',         type: 'number', section: 'BTC' },
    { key: 'KELLY_FRACTION',            label: 'Kelly Fraction',               hint: 'e.g. 0.15 = 15% fractional Kelly',     type: 'number', section: 'BTC' },
    { key: 'MAX_TOTAL_PENDING_TRADES',  label: 'Max Pending Trades',          hint: 'Circuit breaker: max open positions',   type: 'number', section: 'BTC' },
    { key: 'WEATHER_MAX_TRADE_SIZE',    label: 'Weather Max Trade Size ($)',   hint: 'Weather strategy trade cap',            type: 'number', section: 'Weather' },
    { key: 'WEATHER_MIN_EDGE_THRESHOLD',label: 'Weather Min Edge',            hint: 'e.g. 0.08 = 8% edge required',         type: 'number', section: 'Weather' },
  ] as const

  const [values, setValues] = useState<Record<string, string>>({})

  const { data: settings } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: fetchAdminSettings,
  })

  const currentVal = (key: string): string => {
    if (values[key] !== undefined) return values[key]
    const flat = Object.values(settings ?? {}).reduce((acc, sec) => ({ ...acc, ...(sec as object) }), {}) as Record<string, unknown>
    return String(flat[key] ?? '')
  }

  const handleSave = async () => {
    const changed = Object.entries(values).filter(([, v]) => v !== '')
    if (!changed.length) return
    setSaving(true)
    setStatus(null)
    try {
      const updates: Record<string, unknown> = {}
      for (const [k, v] of changed) updates[k] = parseFloat(v) || v
      await updateAdminSettings(updates)
      setStatus({ ok: true, message: `Saved ${changed.length} parameter(s)` })
      setValues({})
      qc.invalidateQueries({ queryKey: ['admin-settings'] })
    } catch {
      setStatus({ ok: false, message: 'Failed to save' })
    } finally {
      setSaving(false)
    }
  }

  const sections = ['Capital', 'BTC', 'Weather'] as const
  const grouped = sections.map(s => ({ section: s, fields: RISK_FIELDS.filter(f => f.section === s) }))

  return (
    <div className="space-y-4">
      {grouped.map(({ section, fields }) => (
        <div key={section} className="border border-neutral-800 bg-neutral-900/20 p-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">{section} Risk</div>
          <div className="grid grid-cols-2 gap-3">
            {fields.map(f => (
              <div key={f.key}>
                <div className="text-[10px] text-neutral-400 mb-1">{f.label}</div>
                <input
                  type="number"
                  step="any"
                  value={currentVal(f.key)}
                  onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={f.hint}
                  className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-green-500/40 focus:outline-none placeholder:text-neutral-700"
                />
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="border border-amber-900/30 bg-amber-950/10 p-3">
        <div className="text-[10px] text-amber-600/80 leading-relaxed">
          Changes take effect immediately (hot-reload). To apply a new bankroll, save then use <span className="font-mono">Bot → Reset</span> in the System tab.
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !Object.values(values).some(v => v !== '')}
          className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
        >
          {saving ? 'Saving...' : 'Save Risk Parameters'}
        </button>
        {status && (
          <span className={`text-[10px] font-mono ${status.ok ? 'text-green-500' : 'text-red-500'}`}>
            {status.message}
          </span>
        )}
      </div>
    </div>
  )
}

const AI_PROVIDERS = [
  { value: 'groq',       label: 'Groq',       needsKey: true,  needsUrl: false },
  { value: 'claude',     label: 'Claude',     needsKey: true,  needsUrl: false },
  { value: 'omniroute',  label: 'OmniRoute',  needsKey: true,  needsUrl: true  },
  { value: 'custom',     label: 'Custom',     needsKey: true,  needsUrl: true  },
] as const

const PROVIDER_DEFAULTS: Record<string, { placeholder: string; modelPlaceholder: string }> = {
  groq:      { placeholder: 'https://api.groq.com/openai/v1', modelPlaceholder: 'llama-3.1-70b-versatile' },
  claude:    { placeholder: 'https://api.anthropic.com',      modelPlaceholder: 'claude-3-5-haiku-20241022' },
  omniroute: { placeholder: 'https://api.omniroute.ai/v1',    modelPlaceholder: 'auto' },
  custom:    { placeholder: 'https://your-api.example.com/v1',modelPlaceholder: 'model-name' },
}

function AITab() {
  const qc = useQueryClient()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Awaited<ReturnType<typeof fetchAISuggest>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyStatus, setApplyStatus] = useState<{ ok: boolean; message: string } | null>(null)

  // Provider config state
  const [providerSaving, setProviderSaving] = useState(false)
  const [providerStatus, setProviderStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [providerFields, setProviderFields] = useState<Record<string, string>>({})

  const { data: settings } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: fetchAdminSettings,
  })

  const flat = Object.values(settings ?? {}).reduce((acc, sec) => ({ ...acc, ...(sec as object) }), {}) as Record<string, unknown>

  const currentProvider = (providerFields['AI_PROVIDER'] ?? String(flat['AI_PROVIDER'] ?? 'groq')) as string
  const providerDef = AI_PROVIDERS.find(p => p.value === currentProvider) ?? AI_PROVIDERS[0]
  const defaults = PROVIDER_DEFAULTS[currentProvider] ?? PROVIDER_DEFAULTS.custom

  const pval = (key: string, fallback = '') =>
    key in providerFields ? providerFields[key] : String(flat[key] ?? fallback)

  const handleProviderField = (key: string, value: string) =>
    setProviderFields(f => ({ ...f, [key]: value }))

  const handleProviderSave = async () => {
    setProviderSaving(true)
    setProviderStatus(null)
    try {
      const updates: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(providerFields)) {
        if (v !== '') updates[k] = v
      }
      await updateAdminSettings(updates)
      setProviderStatus({ ok: true, message: 'Provider saved' })
      setProviderFields({})
      qc.invalidateQueries({ queryKey: ['admin-settings'] })
    } catch {
      setProviderStatus({ ok: false, message: 'Save failed' })
    } finally {
      setProviderSaving(false)
    }
  }

  const handleAnalyze = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await fetchAISuggest()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch AI suggestions')
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    if (!result?.suggestions) return
    setApplying(true)
    setApplyStatus(null)
    try {
      const s = result.suggestions
      const updates: Record<string, unknown> = {}
      if (s.kelly_fraction != null) updates['KELLY_FRACTION'] = s.kelly_fraction
      if (s.min_edge_threshold != null) updates['MIN_EDGE_THRESHOLD'] = s.min_edge_threshold
      if (s.max_trade_size != null) updates['MAX_TRADE_SIZE'] = s.max_trade_size
      if (s.daily_loss_limit != null) updates['DAILY_LOSS_LIMIT'] = s.daily_loss_limit
      await updateAdminSettings(updates)
      setApplyStatus({ ok: true, message: 'Settings applied successfully' })
      qc.invalidateQueries({ queryKey: ['admin-settings'] })
    } catch {
      setApplyStatus({ ok: false, message: 'Failed to apply settings' })
    } finally {
      setApplying(false)
    }
  }

  const confidenceColor = (c: unknown) => {
    if (c === 'high') return 'text-green-400 border-green-500/30 bg-green-500/10'
    if (c === 'medium') return 'text-amber-400 border-amber-500/30 bg-amber-500/10'
    return 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10'
  }

  const paramRows = [
    { key: 'kelly_fraction',      label: 'Kelly Fraction',       settingsKey: 'KELLY_FRACTION' },
    { key: 'min_edge_threshold',  label: 'Min Edge Threshold',   settingsKey: 'MIN_EDGE_THRESHOLD' },
    { key: 'max_trade_size',      label: 'Max Trade Size ($)',    settingsKey: 'MAX_TRADE_SIZE' },
    { key: 'daily_loss_limit',    label: 'Daily Loss Limit ($)',  settingsKey: 'DAILY_LOSS_LIMIT' },
  ]

  return (
    <div className="space-y-4">
      {/* Provider Configuration */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">AI Provider</div>
        <div className="space-y-3">
          {/* Provider selector */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-neutral-600 w-24 shrink-0">Provider</span>
            <div className="flex gap-2 flex-wrap">
              {AI_PROVIDERS.map(p => (
                <button
                  key={p.value}
                  onClick={() => handleProviderField('AI_PROVIDER', p.value)}
                  className={`px-2.5 py-1 text-[10px] uppercase tracking-wider border transition-colors ${
                    currentProvider === p.value
                      ? 'bg-green-500/10 border-green-500/40 text-green-400'
                      : 'bg-neutral-900 border-neutral-700 text-neutral-500 hover:border-neutral-500 hover:text-neutral-300'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Model override */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-neutral-600 w-24 shrink-0">Model</span>
            <input
              type="text"
              value={pval('AI_MODEL')}
              onChange={e => handleProviderField('AI_MODEL', e.target.value)}
              placeholder={defaults.modelPlaceholder}
              className="flex-1 bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-500 focus:outline-none"
            />
          </div>

          {/* Base URL — shown for omniroute/custom */}
          {providerDef.needsUrl && (
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-neutral-600 w-24 shrink-0">Base URL</span>
              <input
                type="text"
                value={pval('AI_BASE_URL')}
                onChange={e => handleProviderField('AI_BASE_URL', e.target.value)}
                placeholder={defaults.placeholder}
                className="flex-1 bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-500 focus:outline-none"
              />
            </div>
          )}

          {/* API Key */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-neutral-600 w-24 shrink-0">
              {currentProvider === 'groq' ? 'Groq Key' : currentProvider === 'claude' ? 'Anthropic Key' : 'API Key'}
            </span>
            <input
              type="password"
              value={pval(currentProvider === 'groq' ? 'GROQ_API_KEY' : currentProvider === 'claude' ? 'ANTHROPIC_API_KEY' : 'AI_API_KEY')}
              onChange={e => handleProviderField(
                currentProvider === 'groq' ? 'GROQ_API_KEY' : currentProvider === 'claude' ? 'ANTHROPIC_API_KEY' : 'AI_API_KEY',
                e.target.value
              )}
              placeholder="sk-..."
              className="flex-1 bg-neutral-900 border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-500 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleProviderSave}
              disabled={providerSaving || Object.keys(providerFields).length === 0}
              className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
            >
              {providerSaving ? 'Saving...' : 'Save Provider'}
            </button>
            {providerStatus && (
              <span className={`text-[10px] font-mono ${providerStatus.ok ? 'text-green-500' : 'text-red-500'}`}>
                {providerStatus.message}
              </span>
            )}
            <span className="text-[9px] text-neutral-700 ml-auto">
              Active: <span className="text-neutral-500 font-mono">{String(flat['AI_PROVIDER'] ?? 'groq')}</span>
              {flat['AI_MODEL'] != null && flat['AI_MODEL'] !== '' && <> / <span className="text-neutral-500 font-mono">{String(flat['AI_MODEL'] as string)}</span></>}
            </span>
          </div>
        </div>
      </div>

      {/* Parameter Optimizer */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">Parameter Optimizer</div>
        <p className="text-[11px] text-neutral-600 mb-4 leading-relaxed">
          Analyzes recent performance data (last 100 trades and decisions) and suggests optimal parameter adjustments using AI.
        </p>
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="px-3 py-1.5 bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] uppercase tracking-wider hover:bg-green-500/20 transition-colors disabled:opacity-40"
        >
          {loading ? 'Analyzing...' : 'Analyze Performance'}
        </button>

        {error && (
          <div className="mt-3 text-[10px] text-red-400 font-mono">{error}</div>
        )}

        {result && (() => {
          const sugg = result.suggestions as Record<string, string | number | null | undefined>
          return (
          <div className="mt-4 space-y-4">
            {/* Suggestions table */}
            <div className="border border-neutral-800">
              <div className="flex items-center justify-between px-3 py-2 border-b border-neutral-800">
                <span className="text-[10px] text-neutral-400 uppercase tracking-wider">Suggestions</span>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] text-neutral-600">Provider: <span className="text-neutral-400">{result.ai_provider}</span></span>
                  {sugg.confidence != null && (
                    <span className={`text-[9px] uppercase px-1.5 py-0.5 border ${confidenceColor(sugg.confidence)}`}>
                      {String(sugg.confidence)} confidence
                    </span>
                  )}
                </div>
              </div>
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="border-b border-neutral-800">
                    <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Parameter</th>
                    <th className="text-right px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Current</th>
                    <th className="text-right px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Suggested</th>
                    <th className="text-left px-3 py-1.5 text-neutral-600 uppercase tracking-wider">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {paramRows.map(row => {
                    const current = Number(flat[row.settingsKey] ?? 0)
                    const suggested = Number(sugg[row.key] ?? current)
                    const delta = suggested - current
                    return (
                      <tr key={row.key} className="border-b border-neutral-800/50">
                        <td className="px-3 py-1.5 text-neutral-300">{row.label}</td>
                        <td className="px-3 py-1.5 text-right text-neutral-500 tabular-nums">{current}</td>
                        <td className="px-3 py-1.5 text-right text-neutral-200 tabular-nums font-semibold">{suggested}</td>
                        <td className={`px-3 py-1.5 tabular-nums ${delta > 0 ? 'text-green-500' : delta < 0 ? 'text-red-500' : 'text-neutral-600'}`}>
                          {delta === 0 ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(4)}`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Reasoning */}
            {sugg.reasoning != null && (
              <div className="border border-neutral-800 bg-neutral-900/20 p-3">
                <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-1.5">Reasoning</div>
                <p className="text-[11px] text-neutral-400 leading-relaxed">{String(sugg.reasoning)}</p>
              </div>
            )}

            {/* Analysis summary */}
            {result.analysis && (
              <div className="border border-neutral-800 bg-neutral-900/20 p-3">
                <div className="text-[9px] text-neutral-600 uppercase tracking-wider mb-2">Performance Analysis</div>
                <div className="grid grid-cols-3 gap-3 text-[10px] font-mono">
                  {Object.entries(result.analysis).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-neutral-600">{k.replace(/_/g, ' ')}: </span>
                      <span className="text-neutral-300 tabular-nums">
                        {typeof v === 'number' ? (k.includes('rate') ? `${(v * 100).toFixed(1)}%` : v.toFixed(2)) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Apply button */}
            <div className="flex items-center gap-3">
              <button
                onClick={handleApply}
                disabled={applying}
                className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
              >
                {applying ? 'Applying...' : 'Apply Suggestions'}
              </button>
              {applyStatus && (
                <span className={`text-[10px] font-mono ${applyStatus.ok ? 'text-green-500' : 'text-red-500'}`}>
                  {applyStatus.message}
                </span>
              )}
            </div>
          </div>
          )
        })()}
      </div>

      {/* System Info */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">System Info</div>
        <div className="space-y-2 text-[11px] text-neutral-400 leading-relaxed">
          <div>
            <span className="text-neutral-600">AI Provider: </span>
            <span className="font-mono text-neutral-300">Groq (llama-3.1-70b-versatile)</span>
          </div>
          <div>
            <span className="text-neutral-600">Groq Configured: </span>
            <span className="font-mono text-neutral-300">Set <span className="text-amber-400">GROQ_API_KEY</span> in .env to enable</span>
          </div>
          <div>
            <span className="text-neutral-600">Fallback: </span>
            <span className="text-neutral-500">Math-based suggestions when AI unavailable</span>
          </div>
        </div>
      </div>
    </div>
  )
}

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
      <NavBar title="Admin Dashboard" />
      {authRequired ? (
        <div className="shrink-0 flex items-center justify-end px-4 py-1.5 border-b border-neutral-800 bg-neutral-950">
          <button
            onClick={logout}
            className="text-[9px] text-neutral-600 hover:text-neutral-400 uppercase tracking-wider transition-colors"
          >
            Logout
          </button>
        </div>
      ) : (
        <ApiKeyBar />
      )}

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
      <div className="flex-1 overflow-y-auto p-4 max-w-4xl">
        {activeTab === 'System' && <SystemStatus />}
        {activeTab === 'Backtest' && <Backtest />}
        {activeTab === 'Risk' && <RiskTab />}
        {activeTab === 'Credentials' && <CredentialsTab />}
        {activeTab === 'Strategies' && <StrategiesTab />}
        {activeTab === 'Settings' && <SettingsEditor />}
        {activeTab === 'Copy Trader' && <CopyTraderMonitor />}
        {activeTab === 'Telegram' && <TelegramTab />}
        {activeTab === 'Market Watch' && <MarketWatchTab />}
        {activeTab === 'Wallet Config' && <WalletConfigTab />}
        {activeTab === 'AI' && <AITab />}
      </div>
    </div>
  )
}
