import { useEffect, useRef, useState, useCallback } from 'react';

type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

export interface UseWebSocketResult<T = unknown> {
  data: T | null;
  status: WSStatus;
  sendMessage: (msg: string) => void;
  reconnectAttempt: number;
  maxReconnectAttempts: number;
}

export interface UseWebSocketOptions {
  topic?: string;
  maxReconnectAttempts?: number;
}

const MAX_RECONNECT_ATTEMPTS = 3;
const BACKOFF_CAP_MS = 32000;

export function useWebSocket<T = unknown>(
  url: string,
  options?: UseWebSocketOptions
): UseWebSocketResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<WSStatus>('connecting');
  const [reconnectAttempt, setReconnectAttempt] = useState<number>(0);
  
  const wsRef = useRef<WebSocket | null>(null);
  const retryTimeoutRef = useRef<number | null>(null);
  const closedByUser = useRef(false);
  const connectionIdRef = useRef(0);
  const reconnectAttemptRef = useRef(0);
  const subscribedTopicsRef = useRef<Set<string>>(new Set());
  const topicRef = useRef<string | undefined>(options?.topic);
  
  const topic = options?.topic;
  const maxReconnectAttempts = options?.maxReconnectAttempts ?? MAX_RECONNECT_ATTEMPTS;

  topicRef.current = topic;

  const connect = useCallback(() => {
    // Clear any pending retry timeout
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    // Check if we've exceeded max reconnection attempts
    if (reconnectAttemptRef.current >= maxReconnectAttempts) {
      setStatus('disconnected');
      return;
    }

    const connectionId = connectionIdRef.current + 1;
    connectionIdRef.current = connectionId;
    setStatus(reconnectAttemptRef.current === 0 ? 'connecting' : 'reconnecting');
    
    try {
      const ws = new window.WebSocket(url);
      wsRef.current = ws;

      const isCurrentConnection = () => (
        connectionIdRef.current === connectionId && wsRef.current === ws
      );

      ws.onopen = () => {
        if (!isCurrentConnection()) return;

        reconnectAttemptRef.current = 0;
        setReconnectAttempt(0);
        setStatus('connected');
        
        const currentTopic = topicRef.current;
        if (currentTopic) {
          subscribedTopicsRef.current.add(currentTopic);
        }

        subscribedTopicsRef.current.forEach((subscribedTopic) => {
          ws.send(JSON.stringify({ action: 'subscribe', topic: subscribedTopic }));
        });
      };

      ws.onmessage = (evt) => {
        if (!isCurrentConnection()) return;

        try {
          setData(JSON.parse(evt.data) as T);
        } catch {
          setData(evt.data as unknown as T);
        }
      };

      ws.onerror = () => {
        // Error will be handled in onclose
      };

      ws.onclose = () => {
        if (!isCurrentConnection()) return;

        if (closedByUser.current) {
          setStatus('disconnected');
          return;
        }

        const nextAttempt = reconnectAttemptRef.current + 1;
        reconnectAttemptRef.current = nextAttempt;
        setReconnectAttempt(nextAttempt);

        if (nextAttempt >= maxReconnectAttempts) {
          setStatus('disconnected');
          return;
        }

        const backoffMs = Math.min(BACKOFF_CAP_MS, 1000 * Math.pow(2, nextAttempt - 1));
        
        setStatus('reconnecting');

        retryTimeoutRef.current = window.setTimeout(() => {
          if (!closedByUser.current) {
            connect();
          }
        }, backoffMs);
      };
    } catch {
      setStatus('disconnected');
    }
  }, [url, maxReconnectAttempts]);

  useEffect(() => {
    closedByUser.current = false;
    reconnectAttemptRef.current = 0;
    setReconnectAttempt(0);
    connect();
    
    return () => {
      closedByUser.current = true;
      connectionIdRef.current += 1;
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendMessage = useCallback((msg: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(msg);
    }
  }, []);

  return { 
    data, 
    status, 
    sendMessage, 
    reconnectAttempt,
    maxReconnectAttempts 
  };
}
