import { useEffect, useRef, useState, useCallback } from 'react';

type WSStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface UseWebSocketResult<T = unknown> {
  data: T | null;
  status: WSStatus;
  sendMessage: (msg: string) => void;
}

export interface UseWebSocketOptions {
  topic?: string;
}

export function useWebSocket<T = unknown>(
  url: string,
  options?: UseWebSocketOptions
): UseWebSocketResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<WSStatus>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number>(0);
  const closedByUser = useRef(false);
  const topic = options?.topic;

  const connect = useCallback(() => {
    setStatus('connecting');
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        retryRef.current = 0;
        setStatus('open');
        
        if (topic) {
          ws.send(JSON.stringify({ action: 'subscribe', topic }));
        }
      };
      ws.onmessage = (evt) => {
        try {
          setData(JSON.parse(evt.data) as T);
        } catch {
          setData(evt.data as unknown as T);
        }
      };
      ws.onerror = () => setStatus('error');
      ws.onclose = () => {
        setStatus('closed');
        if (closedByUser.current) return;
        const backoff = Math.min(30000, 1000 * Math.pow(2, retryRef.current));
        retryRef.current += 1;
        setTimeout(() => { if (!closedByUser.current) connect(); }, backoff);
      };
    } catch {
      setStatus('error');
    }
  }, [url, topic]);

  useEffect(() => {
    closedByUser.current = false;
    connect();
    return () => {
      closedByUser.current = true;
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((msg: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(msg);
    }
  }, []);

  return { data, status, sendMessage };
}
