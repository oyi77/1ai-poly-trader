import { useEffect, useRef, useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { getWsUrl } from '../api';

interface MarketTick {
  market_id: string;
  yes_price: number;
  no_price: number;
  volume: number;
}

const TICK_BUFFER = 10;
export default function LiveMarketView({ url }: { url?: string }) {
  const wsUrl = url || getWsUrl('/ws/markets')
  const { data, status, reconnectAttempt, maxReconnectAttempts } = useWebSocket<MarketTick>(wsUrl, { topic: 'markets' });
  const [ticks, setTicks] = useState<MarketTick[]>([]);
  const prevRef = useRef<MarketTick | null>(null);

  useEffect(() => {
    if (data && data !== prevRef.current) {
      prevRef.current = data;
      setTicks(prev => [data, ...prev].slice(0, TICK_BUFFER));
    }
  }, [data]);

  const connected = status === 'connected';
  const disconnected = status === 'disconnected';
  const reconnecting = status === 'reconnecting';

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-neutral-200 uppercase tracking-wider">Live Markets</h3>
        <span className={`text-[10px] font-medium uppercase px-1.5 py-0.5 rounded ${
          connected
            ? 'bg-green-500/10 text-green-400'
            : disconnected
            ? 'bg-red-500/10 text-red-400'
            : 'bg-yellow-500/10 text-yellow-400'
        }`}>
          {status}
        </span>
      </div>

      {reconnecting && (
        <p className="text-yellow-400 text-sm mb-2">
          Reconnecting... (attempt {reconnectAttempt}/{maxReconnectAttempts})
        </p>
      )}

      {disconnected && (
        <p className="text-red-400 text-sm mb-2">WebSocket disconnected — max reconnection attempts reached</p>
      )}

      {ticks.length === 0 ? (
        <p className="text-gray-400 text-sm">Waiting for market data...</p>
      ) : (
        <ul className="space-y-2">
          {ticks.map((tick, i) => (
            <li
              key={`${tick.market_id}-${i}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-gray-900/60 rounded px-3 py-2 text-xs"
            >
              <span className="text-neutral-200 font-medium truncate max-w-full sm:max-w-[40%]">{tick.market_id}</span>
              <span className="text-green-400">YES {((tick.yes_price ?? 0) * 100).toFixed(1)}¢</span>
              <span className="text-red-400">NO {((tick.no_price ?? 0) * 100).toFixed(1)}¢</span>
              <span className="text-neutral-500">${(tick.volume ?? 0).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
