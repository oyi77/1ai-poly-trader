import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { ModeFilterProvider } from '../contexts/ModeFilterContext'
import { useModeFilter } from '../hooks/useModeFilter'

describe('ModeFilterContext', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Provider', () => {
    it('mounts without error', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current).toBeDefined()
    })

    it('provides context with correct shape', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current).toHaveProperty('selectedMode')
      expect(result.current).toHaveProperty('setSelectedMode')
      expect(typeof result.current.setSelectedMode).toBe('function')
    })
  })

  describe('useModeFilter hook', () => {
    it('returns default mode "all" on first mount', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('throws error when used outside provider', () => {
      expect(() => {
        renderHook(() => useModeFilter())
      }).toThrow('useModeFilter must be used within ModeFilterProvider')
    })

    it('throws error with correct message', () => {
      expect(() => {
        renderHook(() => useModeFilter())
      }).toThrow(/ModeFilterProvider/)
    })
  })

  describe('Mode switching', () => {
    it('setMode updates selectedMode to "paper"', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('paper')
      })
      expect(result.current.selectedMode).toBe('paper')
    })

    it('setMode updates selectedMode to "testnet"', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('testnet')
      })
      expect(result.current.selectedMode).toBe('testnet')
    })

    it('setMode updates selectedMode to "live"', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('live')
      })
      expect(result.current.selectedMode).toBe('live')
    })

    it('setMode can switch between multiple modes', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('paper')
      })
      expect(result.current.selectedMode).toBe('paper')

      act(() => {
        result.current.setSelectedMode('live')
      })
      expect(result.current.selectedMode).toBe('live')

      act(() => {
        result.current.setSelectedMode('all')
      })
      expect(result.current.selectedMode).toBe('all')
    })
  })

  describe('localStorage persistence', () => {
    it('persists mode to localStorage on change', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('paper')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('paper')
    })

    it('persists "testnet" mode to localStorage', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('testnet')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('testnet')
    })

    it('persists "live" mode to localStorage', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('live')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('live')
    })

    it('reads persisted mode from localStorage on mount', () => {
      localStorage.setItem('dashboard_mode_filter', 'paper')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('paper')
    })

    it('reads "testnet" from localStorage on mount', () => {
      localStorage.setItem('dashboard_mode_filter', 'testnet')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('testnet')
    })

    it('reads "live" from localStorage on mount', () => {
      localStorage.setItem('dashboard_mode_filter', 'live')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('live')
    })

    it('persists multiple sequential changes to localStorage', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('paper')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('paper')

      act(() => {
        result.current.setSelectedMode('live')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('live')

      act(() => {
        result.current.setSelectedMode('testnet')
      })
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('testnet')
    })
  })

  describe('Invalid localStorage handling', () => {
    it('defaults to "all" when localStorage has invalid value', () => {
      localStorage.setItem('dashboard_mode_filter', 'invalid')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('defaults to "all" when localStorage has empty string', () => {
      localStorage.setItem('dashboard_mode_filter', '')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('defaults to "all" when localStorage has random string', () => {
      localStorage.setItem('dashboard_mode_filter', 'random_mode')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('defaults to "all" when localStorage has null', () => {
      localStorage.setItem('dashboard_mode_filter', 'null')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('defaults to "all" when localStorage has undefined', () => {
      localStorage.setItem('dashboard_mode_filter', 'undefined')
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('defaults to "all" when localStorage key does not exist', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current.selectedMode).toBe('all')
    })
  })

  describe('Valid mode values', () => {
    it('accepts "all" as valid mode', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('all')
      })
      expect(result.current.selectedMode).toBe('all')
    })

    it('accepts "paper" as valid mode', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('paper')
      })
      expect(result.current.selectedMode).toBe('paper')
    })

    it('accepts "testnet" as valid mode', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('testnet')
      })
      expect(result.current.selectedMode).toBe('testnet')
    })

    it('accepts "live" as valid mode', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      act(() => {
        result.current.setSelectedMode('live')
      })
      expect(result.current.selectedMode).toBe('live')
    })
  })

  describe('Context provider behavior', () => {
    it('provider wraps children correctly', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })
      expect(result.current).toBeDefined()
      expect(result.current.selectedMode).toBe('all')
    })

    it('context value is stable across re-renders', () => {
      const { result, rerender } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })

      const initialValue = result.current

      act(() => {
        result.current.setSelectedMode('paper')
      })

      rerender()

      expect(result.current.selectedMode).toBe('paper')
      expect(typeof result.current.setSelectedMode).toBe('function')
    })
  })

  describe('Edge cases', () => {
    it('handles rapid mode changes', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })

      act(() => {
        result.current.setSelectedMode('paper')
        result.current.setSelectedMode('live')
        result.current.setSelectedMode('testnet')
        result.current.setSelectedMode('all')
      })

      expect(result.current.selectedMode).toBe('all')
      expect(localStorage.getItem('dashboard_mode_filter')).toBe('all')
    })

    it('localStorage persists after multiple changes', () => {
      const { result } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })

      act(() => {
        result.current.setSelectedMode('paper')
      })
      act(() => {
        result.current.setSelectedMode('live')
      })
      act(() => {
        result.current.setSelectedMode('testnet')
      })

      expect(localStorage.getItem('dashboard_mode_filter')).toBe('testnet')
    })

    it('survives localStorage clear and reinitialize', () => {
      const { result: result1 } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })

      act(() => {
        result1.current.setSelectedMode('paper')
      })

      localStorage.clear()

      const { result: result2 } = renderHook(() => useModeFilter(), {
        wrapper: ModeFilterProvider,
      })

      expect(result2.current.selectedMode).toBe('all')
    })
  })
})
