import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, adminApi, fetchAISuggest, fetchAdminSettings, updateAdminSettings } from '../../api'

const AI_PROVIDERS = [
  { value: 'groq',       label: 'Groq (Fast/Cheap)',  needsKey: true,  needsUrl: false },
  { value: 'claude',     label: 'Claude (Deep)',       needsKey: true,  needsUrl: false },
  { value: 'omniroute',  label: 'OmniRoute',           needsKey: true,  needsUrl: true },
  { value: 'custom',     label: 'Custom',              needsKey: true,  needsUrl: true },
] as const

const PROVIDER_DEFAULTS: Record<string, { placeholder: string; modelPlaceholder: string }> = {
  groq:      { placeholder: 'https://api.groq.com/openai/v1', modelPlaceholder: 'llama-3.1-70b-versatile' },
  claude:    { placeholder: 'https://api.anthropic.com',      modelPlaceholder: 'claude-3-5-haiku-20241022' },
  omniroute: { placeholder: 'https://api.omniroute.ai/v1',    modelPlaceholder: 'auto' },
  custom:    { placeholder: 'https://your-api.example.com/v1',modelPlaceholder: 'model-name' },
}

interface AIStatus {
  enabled: boolean
  provider: string
  model: string
  daily_budget: number
  spent_today: number
  remaining: number
  calls_today: number
  signal_weight: number
}

export function AITab() {
  const qc = useQueryClient()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Awaited<ReturnType<typeof fetchAISuggest>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyStatus, setApplyStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [toggling, setToggling] = useState(false)

  // Provider config state
  const [providerSaving, setProviderSaving] = useState(false)
  const [providerStatus, setProviderStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [providerFields, setProviderFields] = useState<Record<string, string>>({})

  const { data: settings } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: fetchAdminSettings,
  })

  const { data: aiStatus } = useQuery<AIStatus>({
    queryKey: ['ai-status'],
    queryFn: async () => {
      const { data } = await api.get('/ai/status')
      return data
    },
    refetchInterval: 10_000,
  })

  const flat = Object.values(settings ?? {}).reduce((acc, sec) => ({ ...acc, ...(sec as object) }), {}) as Record<string, unknown>

  const currentProvider = (providerFields['AI_PROVIDER'] ?? String(flat['AI_PROVIDER'] ?? 'groq')) as string
  const providerDef = AI_PROVIDERS.find(p => p.value === currentProvider) ?? AI_PROVIDERS[0]
  const defaults = PROVIDER_DEFAULTS[currentProvider] ?? PROVIDER_DEFAULTS.custom

  const pval = (key: string, fallback = '') =>
    key in providerFields ? providerFields[key] : String(flat[key] ?? fallback)

  const handleProviderField = (key: string, value: string) =>
    setProviderFields(f => ({ ...f, [key]: value }))

  const handleToggleAI = async () => {
    setToggling(true)
    try {
      await adminApi.post('/ai/toggle')
      qc.invalidateQueries({ queryKey: ['ai-status'] })
    } catch {
      // ignore
    } finally {
      setToggling(false)
    }
  }

  const handleProviderSave = async () => {
    setProviderSaving(true)
    setProviderStatus(null)
    try {
      const updates: Array<{ key: string; value: string }> = []
      for (const [k, v] of Object.entries(providerFields)) {
        if (v !== '') updates.push({ key: k, value: String(v) })
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
      const updates: Array<{ key: string; value: string }> = []
      if (s.kelly_fraction != null) updates.push({ key: 'KELLY_FRACTION', value: String(s.kelly_fraction) })
      if (s.min_edge_threshold != null) updates.push({ key: 'MIN_EDGE_THRESHOLD', value: String(s.min_edge_threshold) })
      if (s.max_trade_size != null) updates.push({ key: 'MAX_TRADE_SIZE', value: String(s.max_trade_size) })
      if (s.daily_loss_limit != null) updates.push({ key: 'DAILY_LOSS_LIMIT', value: String(s.daily_loss_limit) })
      await updateAdminSettings(updates)
      setApplyStatus({ ok: true, message: 'Settings applied successfully' })
      qc.invalidateQueries({ queryKey: ['admin-settings'] })
    } catch {
      setApplyStatus({ ok: false, message: 'Failed to apply settings' })
    } finally {
      setApplying(false)
    }
  }

  const paramRows = [
    { key: 'kelly_fraction',      label: 'Kelly Fraction',       settingsKey: 'KELLY_FRACTION' },
    { key: 'min_edge_threshold',  label: 'Min Edge Threshold',   settingsKey: 'MIN_EDGE_THRESHOLD' },
    { key: 'max_trade_size',      label: 'Max Trade Size ($)',    settingsKey: 'MAX_TRADE_SIZE' },
    { key: 'daily_loss_limit',    label: 'Daily Loss Limit ($)', settingsKey: 'DAILY_LOSS_LIMIT' },
  ]

  const budgetPct = aiStatus ? (aiStatus.spent_today / Math.max(aiStatus.daily_budget, 0.01)) * 100 : 0

  return (
    <div className="space-y-4">
      {/* AI Master Toggle + Status */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider">AI-Enhanced Signals</div>
          <button
            onClick={handleToggleAI}
            disabled={toggling}
            className={`relative w-12 h-6 rounded-full transition-colors ${aiStatus?.enabled ? 'bg-green-500/30 border-green-500/50' : 'bg-neutral-800 border-neutral-700'} border`}
          >
            <span className={`absolute top-0.5 w-5 h-5 rounded-full transition-all ${aiStatus?.enabled ? 'left-6 bg-green-500' : 'left-0.5 bg-neutral-600'}`} />
          </button>
        </div>

        {aiStatus?.enabled ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="border border-neutral-800 p-2">
                <div className="text-[8px] text-neutral-600 uppercase">Provider</div>
                <div className="text-[11px] text-neutral-200 font-mono">{aiStatus.provider}</div>
              </div>
              <div className="border border-neutral-800 p-2">
                <div className="text-[8px] text-neutral-600 uppercase">Calls Today</div>
                <div className="text-[11px] text-neutral-200 font-mono tabular-nums">{aiStatus.calls_today}</div>
              </div>
              <div className="border border-neutral-800 p-2">
                <div className="text-[8px] text-neutral-600 uppercase">Spent</div>
                <div className="text-[11px] text-neutral-200 font-mono tabular-nums">${(aiStatus.spent_today ?? 0).toFixed(4)}</div>
              </div>
              <div className="border border-neutral-800 p-2">
                <div className="text-[8px] text-neutral-600 uppercase">Signal Weight</div>
                <div className="text-[11px] text-amber-400 font-mono tabular-nums">{((aiStatus.signal_weight ?? 0) * 100).toFixed(0)}%</div>
              </div>
            </div>

            {/* Budget bar */}
            <div>
              <div className="flex items-center justify-between text-[9px] mb-1">
                <span className="text-neutral-600">Daily Budget</span>
                <span className="text-neutral-500 tabular-nums">${(aiStatus.spent_today ?? 0).toFixed(3)} / ${(aiStatus.daily_budget ?? 0).toFixed(2)}</span>
              </div>
              <div className="h-1.5 bg-neutral-800 w-full">
                <div
                  className={`h-full transition-all ${budgetPct > 80 ? 'bg-red-500' : budgetPct > 50 ? 'bg-amber-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, budgetPct)}%` }}
                />
              </div>
            </div>

            <div className="text-[9px] text-neutral-600">
              AI analyzes each signal using {aiStatus.provider} before execution. Signals are weighted {((aiStatus.signal_weight ?? 0) * 100).toFixed(0)}% AI / {(((1 - (aiStatus.signal_weight ?? 0)) * 100)).toFixed(0)}% technical.
            </div>
          </div>
        ) : (
          <div className="text-[10px] text-neutral-600">
            AI enhancement is disabled. Signals use technical indicators only. Enable to add AI-powered probability estimation to the signal pipeline.
          </div>
        )}
      </div>

      {/* Provider Config */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">AI Provider</div>
        <div className="space-y-3 mb-4">
          <div>
            <div className="text-[10px] text-neutral-400 mb-1">Provider</div>
            <select
              value={currentProvider}
              onChange={e => handleProviderField('AI_PROVIDER', e.target.value)}
              className="w-full bg-black border border-neutral-700 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-green-500/40 focus:outline-none"
            >
              {AI_PROVIDERS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          {providerDef.needsUrl && (
            <div>
              <div className="text-[10px] text-neutral-400 mb-1">API URL</div>
              <input
                type="text"
                value={pval('AI_API_URL', defaults.placeholder)}
                onChange={e => handleProviderField('AI_API_URL', e.target.value)}
                placeholder={defaults.placeholder}
                className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
              />
            </div>
          )}
          {providerDef.needsKey && (
            <div>
              <div className="text-[10px] text-neutral-400 mb-1">API Key</div>
              <input
                type="password"
                value={pval('AI_API_KEY', '')}
                onChange={e => handleProviderField('AI_API_KEY', e.target.value)}
                placeholder="API key"
                className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
              />
            </div>
          )}
          <div>
            <div className="text-[10px] text-neutral-400 mb-1">Model</div>
            <input
              type="text"
              value={pval('AI_MODEL', defaults.modelPlaceholder)}
              onChange={e => handleProviderField('AI_MODEL', e.target.value)}
              placeholder={defaults.modelPlaceholder}
              className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none placeholder:text-neutral-700"
            />
          </div>
          <div>
            <div className="text-[10px] text-neutral-400 mb-1">Daily Budget ($)</div>
            <input
              type="number"
              step="0.10"
              value={pval('AI_DAILY_BUDGET_USD', '1.0')}
              onChange={e => handleProviderField('AI_DAILY_BUDGET_USD', e.target.value)}
              className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none"
            />
          </div>
          <div>
            <div className="text-[10px] text-neutral-400 mb-1">Signal Weight (0.0 - 0.5)</div>
            <input
              type="number"
              step="0.05"
              min="0"
              max="0.5"
              value={pval('AI_SIGNAL_WEIGHT', '0.30')}
              onChange={e => handleProviderField('AI_SIGNAL_WEIGHT', e.target.value)}
              className="w-full bg-transparent border border-neutral-800 text-neutral-300 text-[10px] px-2 py-1 font-mono focus:border-neutral-600 focus:outline-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleProviderSave}
            disabled={providerSaving}
            className="px-3 py-1 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
          >
            {providerSaving ? 'Saving...' : 'Save Provider'}
          </button>
          {providerStatus && (
            <span className={`text-[10px] font-mono ${providerStatus.ok ? 'text-green-500' : 'text-red-500'}`}>
              {providerStatus.message}
            </span>
          )}
        </div>
      </div>

      {/* AI Risk Analysis */}
      <div className="border border-neutral-800 bg-neutral-900/20 p-4">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">AI Risk Analysis</div>
        <p className="text-[11px] text-neutral-600 mb-4">
          Analyze recent performance and get AI-suggested parameter adjustments.
        </p>
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-[10px] uppercase tracking-wider hover:border-neutral-500 transition-colors disabled:opacity-40"
        >
          {loading ? 'Analyzing...' : 'Analyze Performance'}
        </button>
        {error && <div className="text-[10px] text-red-400 mt-3">{error}</div>}
      </div>

      {/* Results */}
      {result && (
        <div className="border border-neutral-800 bg-neutral-900/20 p-4">
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-3">AI Suggestions</div>
          <div className="space-y-3">
            <div className="text-[11px] text-neutral-400 mb-1">Status</div>
            <div className="text-[11px] text-neutral-600 leading-relaxed mb-4">{result.status}</div>

            <div className="text-[11px] text-neutral-400 mb-2">Parameter Adjustments</div>
            <div className="overflow-x-auto">
            <table className="w-full text-[10px] font-mono min-w-[300px]">
              <thead>
                <tr className="border-b border-neutral-800">
                  <th className="text-left px-2 py-1 text-neutral-600">Parameter</th>
                  <th className="text-left px-2 py-1 text-neutral-600">Current</th>
                  <th className="text-left px-2 py-1 text-neutral-600">Suggested</th>
                </tr>
              </thead>
              <tbody>
                {paramRows.map(r => {
                  const current = parseFloat(pval(r.settingsKey, '0'))
                  const suggested = result.suggestions[r.key]
                  return (
                    <tr key={r.key} className="border-b border-neutral-800/50">
                      <td className="px-2 py-1 text-neutral-400">{r.label}</td>
                      <td className="px-2 py-1 text-neutral-500">{current}</td>
                      <td className={`px-2 py-1 ${suggested !== null ? (suggested > current ? 'text-green-400' : 'text-red-400') : 'text-neutral-500'}`}>
                        {suggested !== null ? String(suggested) : '--'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>

            <div className="text-[11px] text-neutral-400 mb-2 mt-4">Analysis</div>
            {result.analysis && Object.entries(result.analysis).map(([k, v]) => (
              <div key={k} className="text-[10px] text-neutral-600">
                <span className="text-neutral-500">{k}: </span>
                {String(v)}
              </div>
            ))}

            <div className="mt-4 flex items-center gap-2">
              <button
                onClick={handleApply}
                disabled={applying}
                className="px-3 py-1.5 bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] uppercase tracking-wider hover:bg-green-500/20 transition-colors disabled:opacity-40"
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
        </div>
      )}
    </div>
  )
}
