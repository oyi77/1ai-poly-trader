import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useWebSocket } from '../hooks/useWebSocket';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  url: string;
  readyState = 0;
  onopen: ((this: WebSocket, ev: Event) => void) | null = null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => void) | null = null;
  onerror: ((this: WebSocket, ev: Event) => void) | null = null;
  onclose: ((this: WebSocket, ev: CloseEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn(function(this: MockWebSocket) {
    this.readyState = 3;
    setTimeout(() => {
      this.onclose?.call(this as unknown as WebSocket, {} as CloseEvent);
    }, 0);
  });
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.call(this as unknown as WebSocket, {} as Event);
    }, 0);
  }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    (window as unknown as { WebSocket: typeof MockWebSocket }).WebSocket = MockWebSocket;
  });
  
  afterEach(() => { 
    vi.clearAllMocks();
  });

  it('connects and reports connected status', async () => {
    const { result } = renderHook(() => useWebSocket('ws://test'));
    
    expect(result.current.status).toBe('connecting');
    
    await waitFor(() => {
      expect(result.current.status).toBe('connected');
    });
    
    expect(result.current.reconnectAttempt).toBe(0);
  });

  it('parses incoming JSON messages', async () => {
    const { result } = renderHook(() => useWebSocket<{ x: number }>('ws://test'));
    
    await waitFor(() => {
      expect(result.current.status).toBe('connected');
    });
    
    const ws = MockWebSocket.instances[0];
    act(() => {
      ws.onmessage?.call(ws as unknown as WebSocket, { data: '{"x":42}' } as MessageEvent);
    });
    
    expect(result.current.data).toEqual({ x: 42 });
  });

  it('reconnects with exponential backoff on disconnect', async () => {
    vi.useFakeTimers();
    
    const { result } = renderHook(() => useWebSocket('ws://test'));
    
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    
    expect(result.current.status).toBe('connected');
    
    const ws = MockWebSocket.instances[0];
    act(() => {
      ws.close();
    });
    
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    
    expect(result.current.status).toBe('reconnecting');
    expect(result.current.reconnectAttempt).toBe(1);
    
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    
    vi.useRealTimers();
  });

  it('respects max reconnection attempts', async () => {
    vi.useFakeTimers();
    
    const { result } = renderHook(() => 
      useWebSocket('ws://test', { maxReconnectAttempts: 3 })
    );
    
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    
    expect(result.current.status).toBe('connected');
    
    for (let i = 0; i < 3; i++) {
      const ws = MockWebSocket.instances[i];
      act(() => {
        ws.close();
      });
      
      await act(async () => {
        await vi.runAllTimersAsync();
        await vi.advanceTimersByTimeAsync(Math.pow(2, i) * 1000);
      });
    }
    
    expect(result.current.status).toBe('disconnected');
    expect(result.current.reconnectAttempt).toBe(3);
    
    vi.useRealTimers();
  });

  it('subscribes to topic on connect', async () => {
    const { result } = renderHook(() => 
      useWebSocket('ws://test', { topic: 'markets' })
    );
    
    await waitFor(() => {
      expect(result.current.status).toBe('connected');
    });
    
    const ws = MockWebSocket.instances[0];
    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ action: 'subscribe', topic: 'markets' })
    );
  });

  it('resubscribes to topic after reconnection', async () => {
    vi.useFakeTimers();
    
    renderHook(() => 
      useWebSocket('ws://test', { topic: 'markets' })
    );
    
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    
    const ws1 = MockWebSocket.instances[0];
    expect(ws1.send).toHaveBeenCalledTimes(1);
    
    act(() => {
      ws1.close();
    });
    
    await act(async () => {
      await vi.runAllTimersAsync();
      await vi.advanceTimersByTimeAsync(1000);
    });
    
    const ws2 = MockWebSocket.instances[1];
    expect(ws2.send).toHaveBeenCalledWith(
      JSON.stringify({ action: 'subscribe', topic: 'markets' })
    );
    
    vi.useRealTimers();
  });

  it('sends messages only when connected', async () => {
    const { result } = renderHook(() => useWebSocket('ws://test'));
    
    act(() => {
      result.current.sendMessage('test-before-connect');
    });
    
    await waitFor(() => {
      expect(result.current.status).toBe('connected');
    });
    
    const ws = MockWebSocket.instances[0];
    expect(ws.send).not.toHaveBeenCalledWith('test-before-connect');
    
    act(() => {
      result.current.sendMessage('test-after-connect');
    });
    
    expect(ws.send).toHaveBeenCalledWith('test-after-connect');
  });
});
