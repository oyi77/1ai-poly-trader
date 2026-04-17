import { useEffect, useRef, useState } from 'react'
import { getAdminApiKey } from '../api'

export type TradeEvent = {
  type: 'trade_opened' | 'trade_settled' | 'signal_found' | 'connected'
  timestamp: string
  data: Record<string, unknown>
}

export function useTradeEvents(onEvent: (event: TradeEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  // Track the admin key as state so changes cause the effect to re-run
  const [adminKey, setAdminKey] = useState(() => getAdminApiKey())

  // Poll for key changes (e.g. user logs in/out in another tab or on the admin page)
  useEffect(() => {
    const interval = setInterval(() => {
      const current = getAdminApiKey()
      setAdminKey(prev => prev !== current ? current : prev)
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const API_BASE = import.meta.env.VITE_API_URL || ''
    const key = getAdminApiKey()
    const tokenParam = key ? `?token=${encodeURIComponent(key)}` : ''
    let es: EventSource | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout>

    const connect = () => {
      es = new EventSource(`${API_BASE}/api/events/stream${tokenParam}`)

      es.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as TradeEvent
          onEventRef.current(event)
        } catch {
          // ignore malformed events
        }
      }

      es.onerror = () => {
        // Prevent rapid reconnect spam which causes ERR_QUIC_PROTOCOL_ERROR / TOO_MANY_RTOS
        if (es) {
          es.close()
          es = null
        }
        reconnectTimeout = setTimeout(() => {
          connect()
        }, 5000) // Backoff 5s
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimeout)
      if (es) es.close()
    }
  }, [adminKey])
}
