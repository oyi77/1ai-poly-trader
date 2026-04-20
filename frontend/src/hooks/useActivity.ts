import { useQuery } from '@tanstack/react-query'
import type { ActivityLog } from '../types/features'

export function useActivity() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['activities'],
    queryFn: async () => {
      const response = await fetch('/api/activities')
      if (!response.ok) {
        throw new Error('Failed to fetch activities')
      }
      return response.json() as Promise<ActivityLog[]>
    },
    refetchInterval: 5000,
  })

  return {
    activities: data || [],
    loading: isLoading,
    error,
    refetch,
  }
}
