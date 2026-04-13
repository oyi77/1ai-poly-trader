import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchAdminSettings, updateAdminSettings } from '../../api'

const SECRET_KEYWORDS = ['KEY', 'SECRET', 'PASSWORD', 'PASSPHRASE', 'TOKEN', 'PRIVATE']

function isSecret(fieldName: string): boolean {
  return SECRET_KEYWORDS.some(k => fieldName.toUpperCase().includes(k))
}

const SECTION_LABELS: Record<string, string> = {
  trading: 'Trading',
  signals: 'Signal Approval',
  weather: 'Weather',
  risk: 'Risk Management',
  indicators: 'Signal Weights',
  ai: 'AI / LLM',
  api_keys: 'API Keys',
  telegram: 'Telegram',
  web_search: 'Web Search Settings',
  security: 'Security',
  system: 'System',
}

function FieldInput({
  fieldName,
  value,
  onChange,
}: {
  fieldName: string
  value: unknown
  onChange: (val: unknown) => void
}) {
  if (fieldName === 'TRADING_MODE') {
    return (
      <select
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        className="bg-neutral-900 border border-neutral-700 text-neutral-200 text-xs px-2 py-1.5 font-mono focus:border-green-500 focus:outline-none w-full"
      >
        <option value="paper">paper</option>
        <option value="testnet">testnet</option>
        <option value="live">live</option>
      </select>
    )
  }
  if (fieldName === 'SIGNAL_APPROVAL_MODE') {
    return (
      <select
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        className="bg-neutral-900 border border-neutral-700 text-neutral-200 text-xs px-2 py-1.5 font-mono focus:border-green-500 focus:outline-none w-full"
      >
        <option value="manual">Always Ask</option>
        <option value="auto_approve">Auto Approve</option>
        <option value="auto_deny">Auto Deny</option>
      </select>
    )
  }

  if (typeof value === 'boolean') {
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
          value ? 'bg-green-500/30' : 'bg-neutral-700'
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 rounded-full transition-transform ${
            value ? 'translate-x-4.5 bg-green-500' : 'translate-x-0.5 bg-neutral-400'
          }`}
        />
      </button>
    )
  }

  return (
    <input
      type={typeof value === 'number' ? 'number' : 'text'}
      value={String(value)}
      onChange={e => {
        const raw = e.target.value
        if (typeof value === 'number') {
          const parsed = raw.includes('.') ? parseFloat(raw) : parseInt(raw, 10)
          onChange(isNaN(parsed) ? raw : parsed)
        } else {
          onChange(raw)
        }
      }}
      step={typeof value === 'number' && String(value).includes('.') ? '0.01' : undefined}
      className="bg-neutral-900 border border-neutral-700 text-neutral-200 text-xs px-2 py-1.5 font-mono focus:border-green-500 focus:outline-none w-full"
    />
  )
}

function SecretField({
  fieldName,
  value,
  onChange,
}: {
  fieldName: string
  value: unknown
  onChange: (val: unknown) => void
}) {
  const [editing, setEditing] = useState(false)
  const [newValue, setNewValue] = useState('')
  const displayValue = String(value)
  const isEmpty = !displayValue || displayValue === '' || displayValue === 'null' || displayValue === 'None'

  if (editing) {
    return (
      <div className="flex gap-1">
        <input
          type="password"
          value={newValue}
          onChange={e => setNewValue(e.target.value)}
          placeholder={`New ${fieldName}`}
          className="bg-neutral-900 border border-neutral-700 text-neutral-200 text-xs px-2 py-1.5 font-mono focus:border-green-500 focus:outline-none flex-1"
          autoFocus
        />
        <button
          onClick={() => { onChange(newValue); setEditing(false); setNewValue('') }}
          className="px-2 py-1 bg-green-500/10 border border-green-500/30 text-green-400 text-[9px] uppercase tracking-wider hover:bg-green-500/20 transition-colors"
        >
          Set
        </button>
        <button
          onClick={() => { setEditing(false); setNewValue('') }}
          className="px-2 py-1 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[9px] uppercase tracking-wider hover:border-neutral-600 transition-colors"
        >
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-neutral-500 font-mono">
        {isEmpty ? <span className="text-neutral-600 italic">not set</span> : String.fromCharCode(8226).repeat(8)}
      </span>
      <button
        onClick={() => setEditing(true)}
        className="px-2 py-0.5 bg-neutral-800 border border-neutral-700 text-neutral-400 text-[9px] uppercase tracking-wider hover:border-neutral-600 transition-colors"
      >
        Update
      </button>
    </div>
  )
}

function SettingsSection({
  sectionKey,
  fields,
  localChanges,
  onFieldChange,
  onSave,
  isSaving,
}: {
  sectionKey: string
  fields: Record<string, unknown>
  localChanges: Record<string, unknown>
  onFieldChange: (field: string, value: unknown) => void
  onSave: () => void
  isSaving: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)
  const hasChanges = Object.keys(localChanges).some(k => k in fields)
  const label = SECTION_LABELS[sectionKey] || sectionKey

  return (
    <div className="border border-neutral-800 bg-neutral-900/20">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full px-3 py-2 flex items-center justify-between hover:bg-neutral-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-neutral-600">{collapsed ? '+' : '-'}</span>
          <span className="text-[10px] font-bold text-neutral-300 uppercase tracking-wider">{label}</span>
          <span className="text-[9px] text-neutral-600">{Object.keys(fields).length} fields</span>
        </div>
        {hasChanges && (
          <span className="text-[9px] text-amber-400 uppercase">Modified</span>
        )}
      </button>

      {!collapsed && (
        <div className="border-t border-neutral-800 px-3 py-2 space-y-2">
          {Object.entries(fields).map(([fieldName, value]) => {
            const currentValue = fieldName in localChanges ? localChanges[fieldName] : value
            return (
              <div key={fieldName} className="flex items-center gap-3">
                <label className="text-[10px] text-neutral-500 font-mono w-64 shrink-0 truncate" title={fieldName}>
                  {fieldName}
                </label>
                <div className="flex-1">
                  {isSecret(fieldName) ? (
                    <SecretField
                      fieldName={fieldName}
                      value={currentValue}
                      onChange={val => onFieldChange(fieldName, val)}
                    />
                  ) : (
                    <FieldInput
                      fieldName={fieldName}
                      value={currentValue}
                      onChange={val => onFieldChange(fieldName, val)}
                    />
                  )}
                </div>
              </div>
            )
          })}

          {hasChanges && (
            <div className="pt-2 border-t border-neutral-800 flex items-center gap-2">
              <button
                onClick={onSave}
                disabled={isSaving}
                className="px-3 py-1.5 bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] uppercase tracking-wider hover:bg-green-500/20 transition-colors disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save Section'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function SettingsEditor() {
  const queryClient = useQueryClient()
  const [localChanges, setLocalChanges] = useState<Record<string, unknown>>({})
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const { data: settings, isLoading, error } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: fetchAdminSettings,
  })

  const mutation = useMutation({
    mutationFn: updateAdminSettings,
    onSuccess: (result) => {
      setToast({ type: 'success', message: result.message || 'Settings updated' })
      setLocalChanges({})
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
    },
    onError: (err: Error) => {
      setToast({ type: 'error', message: err.message || 'Failed to save settings' })
    },
  })

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const handleFieldChange = (field: string, value: unknown) => {
    setLocalChanges(prev => ({ ...prev, [field]: value }))
  }

  const handleSaveSection = (sectionFields: Record<string, unknown>) => {
    const updates: Record<string, unknown> = {}
    for (const field of Object.keys(sectionFields)) {
      if (field in localChanges) {
        updates[field] = localChanges[field]
      }
    }
    if (Object.keys(updates).length > 0) {
      mutation.mutate(updates)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[10px] text-neutral-500 uppercase tracking-wider">Loading settings...</div>
      </div>
    )
  }

  if (error || !settings) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[10px] text-red-500 uppercase tracking-wider">Failed to load settings</div>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {toast && (
        <div className={`px-3 py-2 border text-[10px] uppercase tracking-wider ${
          toast.type === 'success'
            ? 'bg-green-500/10 border-green-500/30 text-green-400'
            : 'bg-red-500/10 border-red-500/30 text-red-400'
        }`}>
          {toast.message}
        </div>
      )}

      {Object.entries(settings).map(([sectionKey, fields]) => (
        <SettingsSection
          key={sectionKey}
          sectionKey={sectionKey}
          fields={fields as Record<string, unknown>}
          localChanges={localChanges}
          onFieldChange={handleFieldChange}
          onSave={() => handleSaveSection(fields as Record<string, unknown>)}
          isSaving={mutation.isPending}
        />
      ))}
    </div>
  )
}
