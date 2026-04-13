import { useQuery } from '@tanstack/react-query'
import type { WeatherForecast, WeatherSignal } from '../types'
import { platformStyles } from '../utils'
import { fetchWeatherForecasts, fetchWeatherSignals } from '../api'

interface Props {
  forecasts?: WeatherForecast[]
  signals?: WeatherSignal[]
}

function AgreementBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100))
  const color = value > 0.7 ? '#22c55e' : value > 0.5 ? '#d97706' : '#dc2626'
  return (
    <div className="edge-bar w-12">
      <div className="edge-fill" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  )
}

export function WeatherPanel({ forecasts, signals }: Props) {
  const { data: forecastData } = useQuery({
    queryKey: ['weather-forecasts'],
    queryFn: fetchWeatherForecasts,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const { data: signalData } = useQuery({
    queryKey: ['weather-signals'],
    queryFn: fetchWeatherSignals,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const resolvedForecasts = (forecasts && forecasts.length > 0) ? forecasts : (forecastData ?? [])
  const resolvedSignals = (signals && signals.length > 0) ? signals : (signalData ?? [])

  if (resolvedForecasts.length === 0 && resolvedSignals.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-center px-4">
        <div className="text-neutral-600 text-[10px] leading-relaxed">
          No weather data yet — forecasts load every 5 min when weather scanning is active.<br />
          <span className="text-neutral-700">Check Admin &gt; Strategies to verify weather_emos is enabled.</span>
        </div>
      </div>
    )
  }

  const signalsByCity = new Map<string, WeatherSignal[]>()
  resolvedSignals.forEach(s => {
    const existing = signalsByCity.get(s.city_key) || []
    existing.push(s)
    signalsByCity.set(s.city_key, existing)
  })

  return (
    <div className="space-y-1 overflow-y-auto max-h-full">
      {resolvedForecasts.map(f => {
        const citySignals = signalsByCity.get(f.city_key) || []
        const actionable = citySignals.filter(s => s.actionable)
        const bestEdge = citySignals.length > 0
          ? citySignals.reduce((a, b) => Math.abs(a.edge) > Math.abs(b.edge) ? a : b)
          : null

        return (
          <div
            key={f.city_key}
            className={`flex items-center gap-2 px-2 py-1.5 ${
              actionable.length > 0 ? 'border-l-2 border-l-green-500 bg-green-500/5' : 'border-l-2 border-l-transparent'
            }`}
          >
            <div className="w-12 shrink-0">
              <div className="text-[10px] font-medium text-neutral-300">{f.city_name}</div>
            </div>
            <div className="flex-1 flex items-center gap-3 text-[10px] tabular-nums">
              <span className="text-neutral-300">
                {f.mean_high.toFixed(0)}F
                <span className="text-neutral-600 ml-0.5">+/-{f.std_high.toFixed(0)}</span>
              </span>
              <AgreementBar value={f.ensemble_agreement} />
              <span className={`${f.ensemble_agreement > 0.7 ? 'text-green-500' : 'text-amber-500'}`}>
                {(f.ensemble_agreement * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {bestEdge && (
                <span className={`text-[10px] tabular-nums ${bestEdge.edge > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {bestEdge.edge > 0 ? '+' : ''}{(bestEdge.edge * 100).toFixed(1)}%
                </span>
              )}
              {citySignals.length > 0 && citySignals[0].platform && (
                <span className={`platform-badge ${
                  platformStyles[citySignals[0].platform.toLowerCase()]?.badge || 'bg-neutral-800 text-neutral-400 border-neutral-700'
                }`}>
                  {platformStyles[citySignals[0].platform.toLowerCase()]?.icon || '?'}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
