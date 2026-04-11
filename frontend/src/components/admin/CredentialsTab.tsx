import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { updateCredentials, changeAdminPassword, fetchSystemStatus, switchTradingMode } from '../../api'
import { useAuth } from '../../hooks/useAuth'

const MODE_META = {
  paper:   { label: 'Paper',   color: 'text-amber-400',  border: 'border-amber-500/30',  desc: 'Simulated orders, no credentials needed' },
  testnet: { label: 'Testnet', color: 'text-yellow-400', border: 'border-yellow-500/30', desc: 'Real orders on Amoy testnet (chain 80002)' },
  live:    { label: 'Live',    color: 'text-red-400',    border: 'border-red-500/30',    desc: 'Real money on Polygon mainnet' },
} as const

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

export function CredentialsTab() {
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
                }`}>
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
