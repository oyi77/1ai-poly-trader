import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { adminApi } from '../api'
import { Settings as SettingsIcon, Zap, TrendingUp, Shield, Activity } from 'lucide-react'

interface SettingsData {
  mirofish_enabled: boolean
  mirofish_api_url?: string
  mirofish_api_key?: string
  strategies: {
    [key: string]: boolean
  }
  risk: {
    max_position_size: number
    max_portfolio_exposure: number
    kelly_fraction: number
    min_edge_threshold: number
  }
  trading_mode: 'paper' | 'testnet' | 'live'
}

interface TestConnectionState {
  testing: boolean
  success: boolean | null
  error: string | null
}

const STRATEGIES = [
  { key: 'btc_momentum', label: 'BTC Momentum', icon: TrendingUp },
  { key: 'btc_oracle', label: 'BTC Oracle', icon: Activity },
  { key: 'weather_emos', label: 'Weather EMOS', icon: Activity },
  { key: 'copy_trader', label: 'Copy Trader', icon: Activity },
  { key: 'market_maker', label: 'Market Maker', icon: Activity },
  { key: 'kalshi_arb', label: 'Kalshi Arbitrage', icon: Activity },
  { key: 'bond_scanner', label: 'Bond Scanner', icon: Activity },
  { key: 'whale_pnl', label: 'Whale PNL Tracker', icon: Activity },
  { key: 'realtime_scanner', label: 'Realtime Scanner', icon: Activity },
]

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testConnection, setTestConnection] = useState<TestConnectionState>({
    testing: false,
    success: null,
    error: null,
  })

  useEffect(() => {
    loadSettings()
  }, [])

  async function loadSettings() {
    try {
      setLoading(true)
      const { data } = await adminApi.get<SettingsData>('/settings')
      setSettings(data)
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  async function updateSettings(updates: Partial<SettingsData>) {
    if (!settings) return
    try {
      setSaving(true)
      const newSettings = { ...settings, ...updates }
      await adminApi.put('/settings', newSettings)
      setSettings(newSettings)
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  async function testMiroFishConnection() {
    if (!settings?.mirofish_api_url || !settings?.mirofish_api_key) {
      setTestConnection({
        testing: false,
        success: false,
        error: 'Please enter both API URL and API Key',
      })
      return
    }

    try {
      setTestConnection({ testing: true, success: null, error: null })
      const { data } = await adminApi.post('/settings/test-mirofish', {
        api_url: settings.mirofish_api_url,
        api_key: settings.mirofish_api_key,
      })
      
      if (data.success) {
        setTestConnection({ testing: false, success: true, error: null })
      } else {
        setTestConnection({
          testing: false,
          success: false,
          error: data.error || 'Connection failed',
        })
      }
    } catch (err: any) {
      setTestConnection({
        testing: false,
        success: false,
        error: err.response?.data?.detail || 'Connection test failed',
      })
    }
  }

  async function toggleMiroFish() {
    if (!settings) return
    
    // Prevent enabling without valid credentials
    if (!settings.mirofish_enabled) {
      if (!settings.mirofish_api_url || !settings.mirofish_api_key) {
        setError('Please enter API URL and API Key, then test the connection before enabling')
        return
      }
      if (testConnection.success !== true) {
        setError('Please test the connection successfully before enabling MiroFish')
        return
      }
    }
    
    await updateSettings({ mirofish_enabled: !settings.mirofish_enabled })
  }

  async function toggleStrategy(key: string) {
    if (!settings) return
    await updateSettings({
      strategies: {
        ...settings.strategies,
        [key]: !settings.strategies[key],
      },
    })
  }

  async function updateRisk(key: keyof SettingsData['risk'], value: number) {
    if (!settings) return
    await updateSettings({
      risk: {
        ...settings.risk,
        [key]: value,
      },
    })
  }

  async function updateMode(mode: 'paper' | 'testnet' | 'live') {
    await updateSettings({ trading_mode: mode })
  }

  if (loading) {
    return (
      <div className="h-full bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-10 h-10 mx-auto mb-4">
            <div className="absolute inset-0 border-2 border-neutral-800 rounded-full" />
            <div className="absolute inset-0 border-2 border-transparent border-t-green-500 rounded-full animate-spin" />
          </div>
          <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-mono">Loading Settings</div>
        </div>
      </div>
    )
  }

  if (error || !settings) {
    return (
      <div className="h-full bg-black flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-500 text-xs uppercase mb-2 tracking-wider">{error || 'Failed to load'}</div>
          <button onClick={loadSettings} className="px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider hover:border-green-500/40 transition-colors">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full bg-black overflow-y-auto">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 border-b border-neutral-800 pb-4"
        >
          <SettingsIcon className="w-5 h-5 text-green-500" />
          <h1 className="text-xl font-bold text-neutral-100 uppercase tracking-wider font-mono">System Settings</h1>
          {saving && <span className="text-xs text-amber-400 animate-pulse">Saving...</span>}
        </motion.div>

        {/* MiroFish Toggle */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-6"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Zap className={`w-6 h-6 ${settings.mirofish_enabled ? 'text-green-500' : 'text-neutral-600'}`} />
              <div>
                <h2 className="text-sm font-bold text-neutral-100 uppercase tracking-wider">MiroFish AI Brain</h2>
                <p className="text-xs text-neutral-500 mt-1">Multi-agent debate system for trade proposals</p>
              </div>
            </div>
            <button
              onClick={toggleMiroFish}
              disabled={saving}
              className={`relative w-14 h-7 rounded-full transition-colors ${
                settings.mirofish_enabled ? 'bg-green-500' : 'bg-neutral-700'
              }`}
            >
              <span
                className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition-transform ${
                  settings.mirofish_enabled ? 'translate-x-7' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* MiroFish Credentials */}
          {settings.mirofish_enabled && (
            <div className="border-t border-neutral-800 pt-4 space-y-3">
              <div>
                <label className="block text-xs text-neutral-400 mb-1.5">API URL</label>
                <input
                  type="text"
                  value={settings.mirofish_api_url || ''}
                  onChange={(e) => updateSettings({ mirofish_api_url: e.target.value })}
                  disabled={saving}
                  placeholder="https://api.mirofish.ai"
                  className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-xs text-neutral-100 placeholder-neutral-600 focus:border-green-500 focus:outline-none disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-1.5">API Key</label>
                <input
                  type="password"
                  value={settings.mirofish_api_key || ''}
                  onChange={(e) => updateSettings({ mirofish_api_key: e.target.value })}
                  disabled={saving}
                  placeholder="••••••••••••••••"
                  className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-xs text-neutral-100 placeholder-neutral-600 focus:border-green-500 focus:outline-none disabled:opacity-50"
                />
              </div>

              {/* Test Connection Button */}
              <div className="flex items-center gap-3">
                <button
                  onClick={testMiroFishConnection}
                  disabled={testConnection.testing || saving}
                  className="px-4 py-2 bg-neutral-800 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider rounded hover:border-green-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {testConnection.testing ? 'Testing...' : 'Test Connection'}
                </button>
                
                {testConnection.success === true && (
                  <span className="text-green-500 text-xs flex items-center gap-1">
                    <span className="text-lg">✓</span> Connected
                  </span>
                )}
                
                {testConnection.success === false && testConnection.error && (
                  <span className="text-red-400 text-xs">{testConnection.error}</span>
                )}
              </div>
            </div>
          )}
        </motion.div>

        {/* Strategy Grid */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-green-500" />
            <h2 className="text-sm font-bold text-neutral-100 uppercase tracking-wider">Trading Strategies</h2>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {STRATEGIES.map((strategy) => {
              const Icon = strategy.icon
              const enabled = settings.strategies[strategy.key] ?? false
              return (
                <button
                  key={strategy.key}
                  onClick={() => toggleStrategy(strategy.key)}
                  disabled={saving}
                  className={`p-4 border rounded-lg transition-all ${
                    enabled
                      ? 'bg-green-500/10 border-green-500/40 text-green-400'
                      : 'bg-neutral-800 border-neutral-700 text-neutral-500 hover:border-neutral-600'
                  }`}
                >
                  <Icon className="w-5 h-5 mb-2" />
                  <div className="text-xs font-bold uppercase tracking-wider">{strategy.label}</div>
                </button>
              )
            })}
          </div>
        </motion.div>

        {/* Risk Parameters */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-green-500" />
            <h2 className="text-sm font-bold text-neutral-100 uppercase tracking-wider">Risk Management</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="flex items-center justify-between text-xs text-neutral-400 mb-2">
                <span>Max Position Size</span>
                <span className="text-neutral-100 font-mono">{settings.risk.max_position_size.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min="0.01"
                max="1"
                step="0.01"
                value={settings.risk.max_position_size}
                onChange={(e) => updateRisk('max_position_size', parseFloat(e.target.value))}
                disabled={saving}
                className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-xs text-neutral-400 mb-2">
                <span>Max Portfolio Exposure</span>
                <span className="text-neutral-100 font-mono">{settings.risk.max_portfolio_exposure.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={settings.risk.max_portfolio_exposure}
                onChange={(e) => updateRisk('max_portfolio_exposure', parseFloat(e.target.value))}
                disabled={saving}
                className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-xs text-neutral-400 mb-2">
                <span>Kelly Fraction</span>
                <span className="text-neutral-100 font-mono">{settings.risk.kelly_fraction.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={settings.risk.kelly_fraction}
                onChange={(e) => updateRisk('kelly_fraction', parseFloat(e.target.value))}
                disabled={saving}
                className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-xs text-neutral-400 mb-2">
                <span>Min Edge Threshold</span>
                <span className="text-neutral-100 font-mono">{(settings.risk.min_edge_threshold * 100).toFixed(1)}%</span>
              </label>
              <input
                type="range"
                min="0.01"
                max="0.2"
                step="0.01"
                value={settings.risk.min_edge_threshold}
                onChange={(e) => updateRisk('min_edge_threshold', parseFloat(e.target.value))}
                disabled={saving}
                className="w-full h-2 bg-neutral-800 rounded-lg appearance-none cursor-pointer slider"
              />
            </div>
          </div>
        </motion.div>

        {/* Trading Mode */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="bg-neutral-900 border border-neutral-800 rounded-lg p-6"
        >
          <h2 className="text-sm font-bold text-neutral-100 uppercase tracking-wider mb-4">Trading Mode</h2>
          <div className="flex gap-3">
            {(['paper', 'testnet', 'live'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => updateMode(mode)}
                disabled={saving}
                className={`flex-1 py-3 px-4 border rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
                  settings.trading_mode === mode
                    ? mode === 'live'
                      ? 'bg-red-500/10 border-red-500/40 text-red-400'
                      : mode === 'testnet'
                      ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400'
                      : 'bg-amber-500/10 border-amber-500/40 text-amber-400'
                    : 'bg-neutral-800 border-neutral-700 text-neutral-500 hover:border-neutral-600'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
