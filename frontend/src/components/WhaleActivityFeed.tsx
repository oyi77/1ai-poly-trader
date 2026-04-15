import { useEffect, useState } from 'react';
import { api } from '../api';

interface WhaleTx {
  id: number;
  tx_hash: string;
  wallet: string;
  market_id: string | null;
  size_usd: number;
  observed_at: string | null;
}

const REFETCH_INTERVAL = 30_000;

export default function WhaleActivityFeed() {
  const [items, setItems] = useState<WhaleTx[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout>;

    const fetch = () => {
      api.get<WhaleTx[]>('/whales/transactions', { params: { limit: 20 } })
        .then(r => {
          if (!cancelled) {
            setItems(Array.isArray(r.data) ? r.data : []);
            setError(false);
          }
        })
        .catch(() => {
          if (!cancelled) setError(true);
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
            timerId = setTimeout(fetch, REFETCH_INTERVAL);
          }
        });
    };

    fetch();
    return () => {
      cancelled = true;
      clearTimeout(timerId);
    };
  }, []);

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-neutral-200 uppercase tracking-wider mb-3">
        Whale Activity
      </h3>

      {loading && (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-8 bg-gray-700/50 rounded animate-pulse" />
          ))}
        </div>
      )}

      {!loading && error && (
        <p className="text-red-400 text-sm">Failed to load whale activity</p>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="text-gray-400 text-sm">No recent whale trades.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <ul className="space-y-2">
          {items.map(it => (
            <li
              key={it.id}
              className="flex items-center justify-between bg-gray-900/60 rounded px-3 py-2 text-xs"
            >
              <code className="text-neutral-400 font-mono">{it.wallet.slice(0, 10)}…</code>
              {it.market_id && (
                <span className="text-neutral-500 truncate max-w-[30%]">{it.market_id}</span>
              )}
              <span className="text-green-400 font-semibold">${(it.size_usd ?? 0).toLocaleString()}</span>
              {it.observed_at && (
                <span className="text-neutral-600">
                  {new Date(it.observed_at).toLocaleTimeString()}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
