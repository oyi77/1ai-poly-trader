import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { retryFetch } from '../utils/retryFetch'

const installFetchMock = (fetchMock: ReturnType<typeof vi.fn>) => {
  globalThis.fetch = Object.assign(fetchMock, {
    preconnect: vi.fn(),
  }) as unknown as typeof fetch
}

describe('retryFetch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('returns response on first success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: 'success' }),
    })
    installFetchMock(fetchMock)

    const response = await retryFetch('/api/test')
    expect(response.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries on 5xx error with exponential backoff', async () => {
    let callCount = 0
    const fetchMock = vi.fn().mockImplementation(() => {
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
    installFetchMock(fetchMock)

    const promise = retryFetch('/api/test')
    
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(2000)
    
    const response = await promise
    expect(response.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('does not retry on 4xx error', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    })
    installFetchMock(fetchMock)

    const response = await retryFetch('/api/test')
    expect(response.ok).toBe(false)
    expect(response.status).toBe(404)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries on network error', async () => {
    let callCount = 0
    const fetchMock = vi.fn().mockImplementation(() => {
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
    installFetchMock(fetchMock)

    const promise = retryFetch('/api/test')
    await vi.advanceTimersByTimeAsync(1000)
    
    const response = await promise
    expect(response.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('throws after max retries exhausted', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    installFetchMock(fetchMock)

    const promise = retryFetch('/api/test')
    const rejection = promise.catch(error => error)
    
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(4000)

    expect(await rejection).toBeInstanceOf(TypeError)
    expect((await rejection).message).toBe('Failed to fetch')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
