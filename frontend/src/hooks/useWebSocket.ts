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

const MAX_RECONNECT_ATTEMPTS = 10;
const BACKOFF_CAP_MS = 32000; // 32 seconds

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
  const subscribedTopicsRef = useRef<Set<string>>(new Set());
  
  const topic = options?.topic;
  const maxReconnectAttempts = options?.maxReconnectAttempts ?? MAX_RECONNECT_ATTEMPTS;

  const resubscribeToTopics = useCallback((ws: WebSocket) => {
    // Resubscribe to all previously subscribed topics
    subscribedTopicsRef.current.forEach((topic) => {
      ws.send(JSON.stringify({ action: 'subscribe', topic }));
    });
  }, []);

  const connect = useCallback(() => {
    // Clear any pending retry timeout
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    // Check if we've exceeded max reconnection attempts
    if (reconnectAttempt >= maxReconnectAttempts) {
      setStatus('disconnected');
      return;
    }

    setStatus(reconnectAttempt === 0 ? 'connecting' : 'reconnecting');
    
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setReconnectAttempt(0);
        setStatus('connected');
        
        // Subscribe to initial topic if provided
        if (topic) {
          subscribedTopicsRef.current.add(topic);
          ws.send(JSON.stringify({ action: 'subscribe', topic }));
        }

        // Resubscribe to any previously subscribed topics
        resubscribeToTopics(ws);
      };

      ws.onmessage = (evt) => {
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
        if (closedByUser.current) {
          setStatus('disconnected');
          return;
        }

        // Calculate exponential backoff with cap
        const attempt = reconnectAttempt;
        const backoffMs = Math.min(BACKOFF_CAP_MS, 1000 * Math.pow(2, attempt));
        
        setReconnectAttempt(attempt + 1);
        setStatus('reconnecting');

        // Schedule reconnection
        retryTimeoutRef.current = setTimeout(() => {
          if (!closedByUser.current) {
            connect();
          }
        }, backoffMs);
      };
    } catch (error) {
      setStatus('disconnected');
      console.error('WebSocket connection error:', error);
    }
  }, [url, topic, reconnectAttempt, maxReconnectAttempts, resubscribeToTopics]);

  useEffect(() => {
    closedByUser.current = false;
    setReconnectAttempt(0);
    connect();
    
    return () => {
      closedByUser.current = true;
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
      wsRef.current?.close();
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
