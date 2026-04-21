import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { retryFetch } from '../utils/retryFetch'

describe('retryFetch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('returns response on first success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: 'success' }),
    })

    const response = await retryFetch('/api/test')
    expect(response.ok).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('retries on 5xx error with exponential backoff', async () => {
    let callCount = 0
    globalThis.fetch = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount < 3) {
        return Promise.resolve({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ data: 'success' }),
      })
    })

    const promise = retryFetch('/api/test')
    
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(2000)
    
    const response = await promise
    expect(response.ok).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledTimes(3)
  })

  it('does not retry on 4xx error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    })

    const response = await retryFetch('/api/test')
    expect(response.ok).toBe(false)
    expect(response.status).toBe(404)
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('retries on network error', async () => {
    let callCount = 0
    globalThis.fetch = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount < 2) {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ data: 'success' }),
      })
    })

    const promise = retryFetch('/api/test')
    await vi.advanceTimersByTimeAsync(1000)
    
    const response = await promise
    expect(response.ok).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
  })

  it('throws after max retries exhausted', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

    const promise = retryFetch('/api/test')
    
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(4000)

    await expect(promise).rejects.toThrow('Failed to fetch')
    expect(globalThis.fetch).toHaveBeenCalledTimes(3)
  })
})
