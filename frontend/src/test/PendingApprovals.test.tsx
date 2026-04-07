import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import PendingApprovals from '../pages/PendingApprovals'

vi.mock('../api', () => ({
  fetchPendingApprovals: vi.fn().mockResolvedValue([]),
  approvePendingTrade: vi.fn().mockResolvedValue({ id: 1, status: 'approved' }),
  rejectPendingTrade: vi.fn().mockResolvedValue({ id: 1, status: 'rejected' }),
}))

describe('PendingApprovals page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the empty state when no items pending', async () => {
    render(<PendingApprovals />)
    await waitFor(() => {
      expect(screen.getByText(/No pending approvals/i)).toBeInTheDocument()
    })
  })

  it('renders rows and triggers approve when present', async () => {
    const mod = await import('../api')
    vi.mocked(mod.fetchPendingApprovals).mockResolvedValueOnce([
      {
        id: 7,
        market_id: 'BTC-MAR-2026',
        direction: 'BUY',
        size: 50,
        confidence: 0.62,
        signal_data: null,
        status: 'pending',
        created_at: '2026-04-07T14:00:00',
      },
    ])
    render(<PendingApprovals />)
    await waitFor(() => {
      expect(screen.getByText('BTC-MAR-2026')).toBeInTheDocument()
    })
    expect(screen.getByText('62.0%')).toBeInTheDocument()

    const approveBtn = screen.getByRole('button', { name: /approve/i })
    fireEvent.click(approveBtn)
    await waitFor(() => {
      expect(vi.mocked(mod.approvePendingTrade)).toHaveBeenCalledWith(7)
    })
  })

  it('shows an error message on fetch failure', async () => {
    const mod = await import('../api')
    vi.mocked(mod.fetchPendingApprovals).mockRejectedValueOnce(new Error('boom'))
    render(<PendingApprovals />)
    await waitFor(() => {
      expect(screen.getByText(/boom/i)).toBeInTheDocument()
    })
  })
})
