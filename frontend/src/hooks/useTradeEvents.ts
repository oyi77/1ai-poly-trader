import { useEffect, useRef } from 'react'

export type TradeEvent = {
  type: 'trade_opened' | 'trade_settled' | 'signal_found' | 'connected'
  timestamp: string
  data: Record<string, unknown>
}

export function useTradeEvents(onEvent: (event: TradeEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    const API_BASE = import.meta.env.VITE_API_URL || ''
    const es = new EventSource(`${API_BASE}/api/events/stream`)

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as TradeEvent
        onEventRef.current(event)
      } catch {
        // ignore malformed events
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects, no action needed
    }

    return () => es.close()
  }, [])
}
