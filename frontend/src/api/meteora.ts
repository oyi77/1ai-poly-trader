// Meteora DLMM screening API (admin-authed; adminApi attaches credentials)
import { adminApi } from './client'

export interface MeteoraSubscores {
  trading: number | null
  lp: number | null
  fees: number | null
  liquidity: number | null
}

export interface MeteoraCandidate {
  cycle_id: string
  pool_address: string
  name: string
  degen_score: number
  weighted_score: number | null
  subscores: MeteoraSubscores
  rejected: boolean
  reject_reason: string | null
  signal_snapshot: Record<string, unknown> | null
  created_at: string | null
}

export interface ScreenSummary {
  cycle_id: string
  screened: number
  rejected: number
  accepted: number
  top: Array<{
    pool_address: string
    name: string
    degen_score: number
    subscores: Record<string, number>
  }>
}

export interface CycleSummary {
  cycle_id: string
  screened: number
  accepted: number
  rejected: number
  top: Array<{ pool_address: string; name: string; degen_score: number }>
}

export const meteoraAPI = {
  screen: async (
    timeframe = '30m',
    category = 'trending',
    pageSize = 100,
  ): Promise<ScreenSummary> => {
    const { data } = await adminApi.post<ScreenSummary>('/meteora/screen', null, {
      params: { timeframe, category, page_size: pageSize },
    })
    return data
  },

  getCandidates: async (
    limit = 100,
    includeRejected = false,
  ): Promise<MeteoraCandidate[]> => {
    const { data } = await adminApi.get<MeteoraCandidate[]>('/meteora/candidates', {
      params: { limit, include_rejected: includeRejected },
    })
    return data
  },

  getCandidatesForCycle: async (cycleId: string): Promise<MeteoraCandidate[]> => {
    const { data } = await adminApi.get<MeteoraCandidate[]>(
      `/meteora/candidates/${cycleId}`,
    )
    return data
  },

  getLatestCycle: async (): Promise<CycleSummary | null> => {
    const { data } = await adminApi.get<CycleSummary | null>('/meteora/cycles/latest')
    return data
  },
}
