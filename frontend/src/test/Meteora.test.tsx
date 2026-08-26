import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Meteora } from '../pages/Meteora'
import { meteoraAPI } from '../api/meteora'

vi.mock('../api/meteora', () => ({
  meteoraAPI: {
    getCandidates: vi.fn().mockResolvedValue([]),
    getLatestCycle: vi.fn().mockResolvedValue(null),
    getCandidatesForCycle: vi.fn().mockResolvedValue([]),
    screen: vi.fn().mockResolvedValue({
      cycle_id: 'cyc-1',
      screened: 2,
      accepted: 1,
      rejected: 1,
      top: [],
    }),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

const SAMPLE = [
  {
    cycle_id: 'cyc-1',
    pool_address: 'PoolA',
    name: 'GOOD-SOL',
    degen_score: 88.4,
    weighted_score: 92.0,
    subscores: { trading: 0.9, lp: 0.8, fees: 0.7, liquidity: 1.0 },
    rejected: false,
    reject_reason: null,
    signal_snapshot: {},
    created_at: '2026-08-26T00:00:00Z',
  },
  {
    cycle_id: 'cyc-1',
    pool_address: 'PoolB',
    name: 'BAD-SOL',
    degen_score: 12.0,
    weighted_score: null,
    subscores: { trading: 0.1, lp: 0.1, fees: 0.1, liquidity: 0.4 },
    rejected: true,
    reject_reason: 'pool_type damm_v2 not supported',
    signal_snapshot: {},
    created_at: '2026-08-26T00:00:00Z',
  },
]

describe('Meteora page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(meteoraAPI.getCandidates).mockResolvedValue([])
    vi.mocked(meteoraAPI.getLatestCycle).mockResolvedValue(null)
  })

  it('renders empty state before any screening run', async () => {
    render(<Meteora />, { wrapper: createWrapper() })
    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toBeInTheDocument(),
    )
  })

  it('renders sorted candidate rows with subscore bars', async () => {
    vi.mocked(meteoraAPI.getCandidates).mockImplementation(
      async (_limit, includeRejected) => (includeRejected ? SAMPLE : [SAMPLE[0]]),
    )
    render(<Meteora />, { wrapper: createWrapper() })
    await waitFor(() =>
      expect(screen.getByTestId('candidates-table')).toBeInTheDocument(),
    )
    expect(screen.getByText('GOOD-SOL')).toBeInTheDocument()
    // rejected row hidden by default
    expect(screen.queryByText('BAD-SOL')).not.toBeInTheDocument()
  })

  it('shows rejected rows when the toggle is on', async () => {
    vi.mocked(meteoraAPI.getCandidates).mockImplementation(
      async (_limit, includeRejected) => (includeRejected ? SAMPLE : [SAMPLE[0]]),
    )
    render(<Meteora />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByLabelText(/show rejected/i))
    await waitFor(() => expect(screen.getByText('BAD-SOL')).toBeInTheDocument())
    expect(screen.getByTitle('pool_type damm_v2 not supported')).toBeInTheDocument()
  })

  it('fires screen-now and surfaces the summary', async () => {
    render(<Meteora />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByText(/screen now/i))
    await waitFor(() =>
      expect(screen.getByTestId('screen-msg')).toHaveTextContent(
        /1 accepted \/ 1 rejected of 2/,
      ),
    )
    expect(meteoraAPI.screen).toHaveBeenCalledWith('30m', 'trending', 100)
  })

  it('surfaces an error banner when screening fails', async () => {
    vi.mocked(meteoraAPI.screen).mockRejectedValueOnce(new Error('boom'))
    render(<Meteora />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByText(/screen now/i))
    await waitFor(() =>
      expect(screen.getByTestId('screen-msg')).toHaveTextContent(/Screen failed: boom/),
    )
  })
})
