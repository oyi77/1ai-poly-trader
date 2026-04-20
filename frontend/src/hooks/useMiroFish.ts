import { useQuery } from '@tanstack/react-query'
import type { MiroFishSignal } from '../types/features'

export function useMiroFish() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['mirofish-signals'],
    queryFn: async () => {
      const response = await fetch('/api/signals/mirofish')
      if (!response.ok) {
        throw new Error('Failed to fetch MiroFish signals')
      }
      return response.json() as Promise<MiroFishSignal[]>
    },
    refetchInterval: 10000,
  })

  return {
    signals: data || [],
    loading: isLoading,
    error,
    refetch,
  }
}
