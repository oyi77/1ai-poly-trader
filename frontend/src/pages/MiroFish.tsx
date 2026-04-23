import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Play, Square, Pause, RotateCcw, ExternalLink, Activity,
  Clock, AlertTriangle, CheckCircle, Loader2, Wifi, WifiOff,
  Signal, Zap, Shield
} from 'lucide-react'
import {
  fetchMiroFishStatus, mirofishStart, mirofishStop, mirofishPause, mirofishRestart,
} from '../api'

type ServiceState = 'running' | 'paused' | 'stopped'

const STATE_COLORS: Record<ServiceState, { bg: string; text: string; dot: string; border: string }> = {
  running: { bg: 'bg-green-500/10', text: 'text-green-400', dot: 'bg-green-500', border: 'border-green-500/40' },
  paused: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', dot: 'bg-yellow-500', border: 'border-yellow-500/40' },
  stopped: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-500', border: 'border-red-500/40' },
}

function formatUptime(seconds: number | null): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

export default function MiroFish() {
  const queryClient = useQueryClient()
  const [iframeLoading, setIframeLoading] = useState(true)
  const [iframeError, setIframeError] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  const { data: status, isLoading, isError, refetch } = useQuery({
    queryKey: ['mirofish-service-status'],
    queryFn: fetchMiroFishStatus,
    refetchInterval: 5000,
  })

  const state = (status?.state ?? 'stopped') as ServiceState
  const colors = STATE_COLORS[state]

  useEffect(() => {
    if (actionMessage) {
      const timer = setTimeout(() => setActionMessage(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [actionMessage])

  const handleAction = useCallback(async (
    action: () => Promise<{ success: boolean; message: string; state: string }>,
    label: string
  ) => {
    setActionLoading(label)
    setActionMessage(null)
    try {
      const result = await action()
      setActionMessage({
        text: result.message,
        type: result.success ? 'success' : 'error',
      })
      queryClient.invalidateQueries({ queryKey: ['mirofish-service-status'] })
    } catch (err: any) {
      setActionMessage({
        text: err.response?.data?.detail || `${label} failed`,
        type: 'error',
      })
    } finally {
      setActionLoading(null)
    }
  }, [queryClient])

  const monitor = status?.monitor
  const cbState = monitor?.circuit_breaker_state ?? 'UNKNOWN'
  const cbIsOpen = cbState === 'OPEN'

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-green-500 mx-auto mb-4" />
          <p className="text-neutral-400 text-xs uppercase tracking-widest">Loading MiroFish</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col bg-black">
      {/* Header */}
      <div className="px-6 py-4 border-b border-neutral-800 bg-neutral-950">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-3 h-3 rounded-full ${colors.dot} ${state === 'running' ? 'animate-pulse' : ''}`} />
            <div>
              <h1 className="text-lg font-bold text-white tracking-wide">MiroFish Service</h1>
              <p className="text-xs text-neutral-500 mt-0.5">Multi-agent prediction engine &middot; Signal integration</p>
            </div>
            <span className={`ml-2 px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${colors.bg} ${colors.text} ${colors.border} border`}>
              {state}
            </span>
          </div>
          <button
            onClick={() => window.open('https://polyedge-mirofish.aitradepulse.com', '_blank')}
            className="flex items-center gap-2 px-3 py-1.5 bg-neutral-800 border border-neutral-700 rounded text-xs text-neutral-300 uppercase tracking-wider hover:border-green-500/40 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open MiroFish UI
          </button>
        </div>
      </div>

      {/* Action Message Toast */}
      {actionMessage && (
        <div className={`px-6 py-2 text-xs flex items-center gap-2 ${
          actionMessage.type === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
        }`}>
          {actionMessage.type === 'success' ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
          {actionMessage.text}
        </div>
      )}

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Panel: Controls & Metrics */}
        <div className="w-full md:w-80 flex-shrink-0 md:border-r border-b md:border-b-0 border-neutral-800 bg-neutral-950 overflow-y-auto md:max-h-full max-h-[40vh]">
          {/* Service Controls */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest mb-3">Service Control</h2>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => handleAction(mirofishStart, 'Start')}
                disabled={actionLoading !== null || state === 'running'}
                className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 hover:border-green-500/50"
              >
                {actionLoading === 'Start' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Start
              </button>
              <button
                onClick={() => handleAction(mirofishStop, 'Stop')}
                disabled={actionLoading !== null || state === 'stopped'}
                className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 hover:border-red-500/50"
              >
                {actionLoading === 'Stop' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
                Stop
              </button>
              <button
                onClick={() => handleAction(mirofishPause, 'Pause')}
                disabled={actionLoading !== null || state !== 'running'}
                className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20 hover:border-yellow-500/50"
              >
                {actionLoading === 'Pause' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Pause className="w-3.5 h-3.5" />}
                Pause
              </button>
              <button
                onClick={() => handleAction(mirofishRestart, 'Restart')}
                disabled={actionLoading !== null}
                className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 hover:border-blue-500/50"
              >
                {actionLoading === 'Restart' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                Restart
              </button>
            </div>
          </div>

          {/* Health Metrics */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest mb-3">Health Metrics</h2>

            {isError || !monitor ? (
              <div className="text-xs text-neutral-600">No monitor data available</div>
            ) : (
              <div className="space-y-3">
                {/* Health Status */}
                <MetricRow
                  icon={<Activity className="w-3.5 h-3.5" />}
                  label="Health"
                  value={monitor.health_status}
                  valueColor={monitor.health_status === 'healthy' ? 'text-green-400' : 'text-red-400'}
                />

                {/* Circuit Breaker */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-neutral-400">
                    <Shield className="w-3.5 h-3.5" />
                    <span className="text-xs">Circuit Breaker</span>
                  </div>
                  <span className={`text-xs font-mono font-bold ${cbIsOpen ? 'text-red-400' : 'text-green-400'}`}>
                    {cbState}
                  </span>
                </div>

                {/* Latency */}
                <MetricRow
                  icon={<Clock className="w-3.5 h-3.5" />}
                  label="Latency"
                  value={monitor.latency_ms > 0 ? `${monitor.latency_ms.toFixed(0)}ms` : '—'}
                  valueColor={monitor.latency_ms > 5000 ? 'text-red-400' : monitor.latency_ms > 1000 ? 'text-yellow-400' : 'text-green-400'}
                />

                {/* Error Rate */}
                <MetricRow
                  icon={<AlertTriangle className="w-3.5 h-3.5" />}
                  label="Error Rate"
                  value={`${monitor.error_rate.toFixed(1)}%`}
                  valueColor={monitor.error_rate > 10 ? 'text-red-400' : monitor.error_rate > 5 ? 'text-yellow-400' : 'text-green-400'}
                />

                {/* Requests */}
                <MetricRow
                  icon={<Signal className="w-3.5 h-3.5" />}
                  label="Requests"
                  value={`${monitor.failed_requests}/${monitor.total_requests}`}
                />

                {/* Consecutive Failures */}
                <MetricRow
                  icon={<WifiOff className="w-3.5 h-3.5" />}
                  label="Failures"
                  value={String(monitor.consecutive_failures)}
                  valueColor={monitor.consecutive_failures > 2 ? 'text-red-400' : 'text-neutral-300'}
                />
              </div>
            )}
          </div>

          {/* Service Info */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest mb-3">Service Info</h2>
            <div className="space-y-2">
              <InfoRow label="Uptime" value={formatUptime(status?.uptime_seconds ?? null)} />
              <InfoRow label="Started" value={formatTimestamp(status?.started_at ?? null)} />
              <InfoRow label="Last Fetch" value={formatTimestamp(status?.last_signal_fetch ?? null)} />
              <InfoRow label="Signals" value={String(status?.total_signals_fetched ?? 0)} />
              {status?.error_message && (
                <div className="mt-2 px-2 py-1.5 bg-red-500/10 border border-red-500/20 rounded text-[10px] text-red-400">
                  {status.error_message}
                </div>
              )}
            </div>
          </div>

          {/* Connection Status */}
          <div className="p-4">
            <h2 className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest mb-3">Connection</h2>
            <div className="flex items-center gap-2">
              {state === 'running' ? (
                <Wifi className="w-4 h-4 text-green-500" />
              ) : (
                <WifiOff className="w-4 h-4 text-neutral-600" />
              )}
              <span className={`text-xs ${state === 'running' ? 'text-green-400' : 'text-neutral-500'}`}>
                {state === 'running' ? 'Connected' : state === 'paused' ? 'Paused' : 'Disconnected'}
              </span>
            </div>
            <p className="text-[10px] text-neutral-600 mt-2">
              MiroFish frontend at <code className="text-blue-400">polyedge-mirofish.aitradepulse.com</code>
            </p>
          </div>
        </div>

        {/* Right Panel: MiroFish iframe */}
        <div className="flex-1 flex flex-col bg-neutral-900">
          {state === 'stopped' ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-sm">
                <Zap className="w-12 h-12 text-neutral-700 mx-auto mb-4" />
                <h2 className="text-lg font-semibold text-neutral-400 mb-2">MiroFish Not Active</h2>
                <p className="text-xs text-neutral-600 mb-6">
                  Start the MiroFish service to enable multi-agent prediction signals
                  and access the simulation dashboard.
                </p>
                <button
                  onClick={() => handleAction(mirofishStart, 'Start')}
                  disabled={actionLoading !== null}
                  className="px-6 py-2.5 bg-green-500/10 border border-green-500/30 rounded text-xs font-bold text-green-400 uppercase tracking-wider hover:bg-green-500/20 hover:border-green-500/50 transition-all disabled:opacity-50"
                >
                  {actionLoading === 'Start' ? <Loader2 className="w-3.5 h-3.5 animate-spin inline mr-2" /> : <Play className="w-3.5 h-3.5 inline mr-2" />}
                  Start Service
                </button>
              </div>
            </div>
          ) : (
            <>
              {iframeLoading && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center">
                    <Loader2 className="w-6 h-6 animate-spin text-green-500 mx-auto mb-3" />
                    <p className="text-xs text-neutral-500">Loading MiroFish simulation...</p>
                  </div>
                </div>
              )}
              {iframeError && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center max-w-sm">
                    <AlertTriangle className="w-10 h-10 text-yellow-500 mx-auto mb-3" />
                    <h3 className="text-sm font-semibold text-neutral-300 mb-1">UI Unavailable</h3>
                    <p className="text-xs text-neutral-500 mb-4">
                      MiroFish service is {state} but the UI failed to load. The signal integration may still be working.
                    </p>
                    <button
                      onClick={() => { setIframeError(false); setIframeLoading(true) }}
                      className="px-4 py-2 bg-neutral-800 border border-neutral-700 rounded text-xs text-neutral-300 uppercase tracking-wider hover:border-green-500/40 transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              )}
              <iframe
                src="https://polyedge-mirofish.aitradepulse.com"
                className={`flex-1 w-full border-0 ${iframeLoading || iframeError ? 'hidden' : ''}`}
                title="MiroFish Simulation"
                onLoad={() => { setIframeLoading(false); setIframeError(false) }}
                onError={() => { setIframeLoading(false); setIframeError(true) }}
                sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
              />
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-2 border-t border-neutral-800 bg-neutral-950 flex justify-between items-center">
        <span className="text-[10px] text-neutral-600">
          MiroFish: Multi-agent simulation for prediction markets
        </span>
        <div className="flex items-center gap-3">
          <button onClick={() => refetch()} className="text-[10px] text-neutral-600 hover:text-neutral-400 transition-colors">
            Refresh
          </button>
          <span className="text-[10px]">
            Status: <span className={colors.text}>{state}</span>
          </span>
        </div>
      </div>
    </div>
  )
}

function MetricRow({ icon, label, value, valueColor = 'text-neutral-300' }: {
  icon: React.ReactNode
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-neutral-400">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span className={`text-xs font-mono ${valueColor}`}>{value}</span>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-neutral-500">{label}</span>
      <span className="text-xs text-neutral-300 font-mono">{value}</span>
    </div>
  )
}
