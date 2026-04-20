import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchAdminSettings, updateAdminSettings } from '../../api'

export function RiskTab() {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null)

  const RISK_FIELDS = [
    { key: 'INITIAL_BANKROLL',          label: 'Initial Bankroll ($)',         hint: 'Starting capital (used on reset)',       type: 'number', section: 'Capital' },
    { key: 'DAILY_LOSS_LIMIT',          label: 'Daily Loss Limit ($)',         hint: 'Stop trading if daily PNL drops below', type: 'number', section: 'Capital' },
    { key: 'MAX_POSITION_FRACTION',     label: 'Max Position Fraction',       hint: 'e.g. 0.08 = 8% of bankroll per trade',  type: 'number', section: 'Capital' },
    { key: 'MAX_TOTAL_EXPOSURE_FRACTION', label: 'Max Exposure Fraction',     hint: 'e.g. 0.70 = 70% total portfolio',       type: 'number', section: 'Capital' },
    { key: 'SLIPPAGE_TOLERANCE',        label: 'Slippage Tolerance',          hint: 'e.g. 0.02 = 2% max slippage',           type: 'number', section: 'Capital' },
    { key: 'DAILY_DRAWDOWN_LIMIT_PCT',  label: 'Daily Drawdown Limit (%)',    hint: 'e.g. 0.10 = 10% max daily loss',        type: 'number', section: 'Capital' },
    { key: 'WEEKLY_DRAWDOWN_LIMIT_PCT', label: 'Weekly Drawdown Limit (%)',  hint: 'e.g. 0.20 = 20% max weekly loss',       type: 'number', section: 'Capital' },
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
      const updates: Array<{ key: string; value: string }> = []
      for (const [k, v] of changed) {
        updates.push({ key: k, value: String(parseFloat(v) || v) })
      }
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
