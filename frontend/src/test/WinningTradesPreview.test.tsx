import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WinningTradesPreview } from '../components/dashboard/WinningTradesPreview'

const trades = [
  {
    id: 1,
    market_ticker: 'BTC-UP-WIN',
    direction: 'up',
    entry_price: 0.55,
    exit_price: 1,
    pnl: 12.5,
    timestamp: '2026-04-27T00:00:00Z',
    trading_mode: 'live',
  },
  {
    id: 2,
    market_ticker: 'BTC-DOWN-LOSS',
    direction: 'down',
    entry_price: 0.45,
    exit_price: 0,
    pnl: -8.25,
    timestamp: '2026-04-27T01:00:00Z',
    trading_mode: 'paper',
  },
]

describe('WinningTradesPreview', () => {
  it('shows only profitable trades by default', () => {
    render(<WinningTradesPreview trades={trades} />)

    expect(screen.getByText('BTC-UP-WIN')).toBeInTheDocument()
    expect(screen.queryByText('BTC-DOWN-LOSS')).not.toBeInTheDocument()
    expect(screen.getByText('+$12.50')).toBeInTheDocument()
  })

  it('shows loss trades when configured for losses', () => {
    render(<WinningTradesPreview trades={trades} title="Worst Loss Trades" variant="losses" />)

    expect(screen.getByText('Worst Loss Trades')).toBeInTheDocument()
    expect(screen.getByText('BTC-DOWN-LOSS')).toBeInTheDocument()
    expect(screen.queryByText('BTC-UP-WIN')).not.toBeInTheDocument()
    expect(screen.getByText('-$8.25')).toBeInTheDocument()
    expect(screen.getByText('paper')).toBeInTheDocument()
  })
})
