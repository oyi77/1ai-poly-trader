import axios from 'axios'
import type { DashboardData, Signal, Trade, BotStats, BtcPrice, BtcWindow, WeatherForecast, WeatherSignal } from './types'

// Empty string = relative URL (uses vite proxy in preview, same-origin in prod)
// Set VITE_API_URL to override (e.g. for local dev pointing at remote API)
const API_BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 15000,
})

// Admin API instance — injects Authorization header from localStorage
export const adminApi = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 15000,
})

adminApi.interceptors.request.use(config => {
  const key = localStorage.getItem('adminApiKey')
  if (key) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${key}`
  }
  return config
})

export function getAdminApiKey(): string {
  return localStorage.getItem('adminApiKey') ?? ''
}

export function setAdminApiKey(key: string) {
  if (key) localStorage.setItem('adminApiKey', key)
  else localStorage.removeItem('adminApiKey')
}

export async function fetchDashboard(): Promise<DashboardData> {
  const { data } = await api.get<DashboardData>('/dashboard')
  return data
}

export async function fetchSignals(): Promise<Signal[]> {
  const { data } = await api.get<Signal[]>('/signals')
  return data
}

export async function fetchBtcPrice(): Promise<BtcPrice | null> {
  const { data } = await api.get<BtcPrice | null>('/btc/price')
  return data
}

export async function fetchBtcWindows(): Promise<BtcWindow[]> {
  const { data } = await api.get<BtcWindow[]>('/btc/windows')
  return data
}

export async function fetchTrades(): Promise<Trade[]> {
  const { data } = await api.get<Trade[]>('/trades', { params: { limit: 10000 } })
  return data
}

export async function fetchStats(): Promise<BotStats> {
  const { data } = await api.get<BotStats>('/stats')
  return data
}

export interface PolymarketMarket {
  ticker: string
  slug: string
  question: string
  category: string
  yes_price: number
  no_price: number
  volume: number
  liquidity: number
  end_date: string | null
}

export interface PolymarketMarketsResponse {
  markets: PolymarketMarket[]
  total: number
  offset: number
  limit: number
}

export async function fetchPolymarketMarkets(offset = 0, limit = 100, category?: string): Promise<PolymarketMarket[]> {
  const { data } = await api.get<PolymarketMarketsResponse>('/polymarket/markets', {
    params: { offset, limit, category }
  })
  return data.markets
}

export async function runScan(): Promise<{ total_signals: number; actionable_signals: number }> {
  const { data } = await adminApi.post('/run-scan')
  return data
}

export async function simulateTrade(ticker: string): Promise<{ trade_id: number; size: number }> {
  const { data } = await adminApi.post('/simulate-trade', null, {
    params: { signal_ticker: ticker }
  })
  return data
}

export async function startBot(): Promise<{ status: string; is_running: boolean }> {
  const { data } = await adminApi.post('/bot/start')
  return data
}

export async function stopBot(): Promise<{ status: string; is_running: boolean }> {
  const { data } = await adminApi.post('/bot/stop')
  return data
}

export async function settleTradesApi(): Promise<{ settled_count: number }> {
  const { data } = await adminApi.post('/settle-trades')
  return data
}

export async function resetBot(): Promise<{ status: string; trades_deleted: number; new_bankroll: number }> {
  const { data } = await adminApi.post('/bot/reset')
  return data
}

export async function fetchBacktestStrategies(): Promise<{
  strategies: Array<{
    name: string
    description: string
    category: string
    default_params: Record<string, any>
  }>
}> {
  const { data } = await api.get('/backtest/strategies')
  return data
}

export async function fetchBacktestHistory(params?: {
  limit?: number
  offset?: number
}): Promise<{
  runs: Array<any>
  total: number
  limit: number
  offset: number
}> {
  const { data } = await api.get('/backtest/history', { params })
  return data
}

export async function runBacktest(config: {
  strategy_name: string
  start_date?: string
  end_date?: string
  initial_bankroll?: number
  params?: Record<string, any>
}): Promise<{
  strategy_name: string
  start_date: string
  end_date: string
  initial_bankroll: number
  results: {
    summary: {
      total_signals: number
      total_trades: number
      winning_trades: number
      losing_trades: number
      win_rate: number
      initial_bankroll: number
      final_equity: number
      total_pnl: number
      total_return_pct: number
      sharpe_ratio: number
    }
    trade_log: Array<{
      entry_price: number
      exit_price: number
      size: number
      pnl: number
      result: string
      timestamp: string
      bankroll_after_trade: number
    }>
    equity_curve: Array<{
      timestamp: string
      equity: number
      pnl: number
    }>
  }
  run_id?: number
}> {
  const { data } = await adminApi.post('/backtest/run', config)
  return data
}

export interface SignalHistoryRow {
  id: number
  market_ticker: string
  platform: string
  market_type: string
  timestamp: string | null
  direction: string
  model_probability: number
  market_probability: number
  edge: number
  confidence: number | null
  suggested_size: number | null
  reasoning: string | null
  executed: boolean
  actual_outcome: string | null
  outcome_correct: boolean | null
  settlement_value: number | null
  settled_at: string | null
}

export async function fetchSignalHistory(params?: { limit?: number; offset?: number; market_type?: string; direction?: string }): Promise<{ items: SignalHistoryRow[]; total: number }> {
  const { data } = await api.get('/signals/history', { params })
  return data
}

export async function fetchWeatherForecasts(): Promise<WeatherForecast[]> {
  const { data } = await api.get<WeatherForecast[]>('/weather/forecasts')
  return data
}

export async function fetchWeatherSignals(): Promise<WeatherSignal[]> {
  const { data } = await api.get<WeatherSignal[]>('/weather/signals')
  return data
}

export async function changeAdminPassword(newPassword: string): Promise<{ status: string; message: string }> {
  const { data } = await adminApi.post('/admin/change-password', { new_password: newPassword })
  return data
}

// Admin API (uses adminApi which injects Authorization header)
export async function fetchAdminSettings(): Promise<Record<string, Record<string, unknown>>> {
  const { data } = await adminApi.get('/admin/settings')
  return data
}

export async function updateAdminSettings(updates: Record<string, unknown>): Promise<{ status: string; message: string }> {
  const { data } = await adminApi.post('/admin/settings', { updates })
  return data
}

export async function switchTradingMode(mode: 'paper' | 'testnet' | 'live'): Promise<{ status: string; mode: string }> {
  const { data } = await adminApi.post('/admin/mode', { mode })
  return data
}

export async function updateCredentials(creds: {
  private_key?: string
  api_key?: string
  api_secret?: string
  api_passphrase?: string
}): Promise<{
  status: string
  updated: string[]
  creds_paper: boolean
  creds_testnet: boolean
  creds_live: boolean
  missing_for_testnet: string[]
  missing_for_live: string[]
}> {
  const { data } = await adminApi.post('/admin/credentials', creds)
  return data
}

export async function fetchSystemStatus(): Promise<{
  trading_mode: string
  bot_running: boolean
  uptime_seconds: number
  pending_trades: number
  telegram_configured: boolean
  kalshi_enabled: boolean
  weather_enabled: boolean
  db_trade_count: number
  db_signal_count: number
  creds_paper: boolean
  creds_testnet: boolean
  creds_live: boolean
  missing_for_testnet: string[]
  missing_for_live: string[]
}> {
  const { data } = await adminApi.get('/admin/system')
  return data
}

export async function fetchCopyTraderStatus(): Promise<{
  enabled: boolean
  tracked_wallets: number
  wallet_details: Array<{ address: string; pseudonym: string; score: number; profit_30d: number }>
  recent_signals: Array<Record<string, unknown>>
  status: string
  errors: Array<{ source: string; message: string }>
}> {
  const { data } = await adminApi.get('/copy-trader/status')
  return data
}

export interface CopyTraderPosition {
  wallet: string
  condition_id: string
  side: string
  size: number
  opened_at: string | null
}

export async function fetchCopyTraderPositions(): Promise<CopyTraderPosition[]> {
  const { data } = await adminApi.get<CopyTraderPosition[]>('/copy-trader/positions')
  return data
}

export interface SettlementEvent {
  id: number
  trade_id: number
  market_ticker: string
  resolved_outcome: string | null
  pnl: number | null
  settled_at: string | null
  source: string
}

export async function fetchSettlements(limit = 100, offset = 0): Promise<SettlementEvent[]> {
  const { data } = await api.get<SettlementEvent[]>('/settlements', { params: { limit, offset } })
  return data
}

// ── Leaderboard / Whale Tracker ──────────────────────────────────────────────

export interface ScoredTrader {
  wallet: string
  pseudonym: string
  profit_30d: number
  win_rate: number
  total_trades: number
  unique_markets: number
  estimated_bankroll: number
  score: number
  market_diversity: number
}

export async function fetchCopyLeaderboard(): Promise<ScoredTrader[]> {
  const { data } = await adminApi.get<ScoredTrader[]>('/copy/leaderboard', { params: { limit: 100 } })
  return data
}

// ── Wallet Config ─────────────────────────────────────────────────────────────

export interface WalletConfigRow {
  id: number
  address: string
  pseudonym: string
  source: string
  tags: string[]
  enabled: boolean
  added_at: string | null
}

export async function fetchWalletConfigs(params?: Record<string, string | number | boolean>): Promise<{ items: WalletConfigRow[]; total: number }> {
  const { data } = await adminApi.get('/wallets/config', { params })
  return data
}

export async function createWalletConfig(body: { address: string; pseudonym?: string; source?: string; tags?: string[]; enabled?: boolean }): Promise<WalletConfigRow> {
  const { data } = await adminApi.post('/wallets/config', body)
  return data
}

export async function updateWalletConfig(id: number, body: Partial<{ pseudonym: string; tags: string[]; enabled: boolean; notes: string }>): Promise<WalletConfigRow> {
  const { data } = await adminApi.put(`/wallets/config/${id}`, body)
  return data
}

export async function deleteWalletConfig(id: number): Promise<void> {
  await adminApi.delete(`/wallets/config/${id}`)
}

export interface CreatedWallet {
  address: string
  private_key: string
  /** WARNING: Save this key securely. Never share or commit to repo. */
}

export async function createWallet(): Promise<CreatedWallet> {
  const { data } = await adminApi.post<CreatedWallet>('/wallets/create')
  return data
}

export interface ActiveWallet {
  active_wallet: string | null
}

export async function getActiveWallet(): Promise<ActiveWallet> {
  const { data } = await adminApi.get<ActiveWallet>('/wallets/active')
  return data
}

export async function setActiveWallet(address: string): Promise<{ active_wallet: string }> {
  const { data } = await adminApi.put<{ active_wallet: string }>('/wallets/active', { address })
  return data
}

export interface WalletBalance {
  address: string
  usdc_balance: number
  last_updated: string | null
  source: 'cache' | 'polymarket' | 'error' | 'none'
  error?: string
}

export async function getWalletBalance(address: string, forceRefresh = false): Promise<WalletBalance> {
  const { data } = await adminApi.get<WalletBalance>(`/wallets/${address}/balance`, {
    params: { force_refresh: forceRefresh }
  })
  return data
}

export async function updateWalletBalance(address: string, balance: number): Promise<WalletBalance> {
  const { data } = await adminApi.put<WalletBalance>(`/wallets/${address}/balance`, {
    usdc_balance: balance,
    last_updated: new Date().toISOString()
  })
  return data
}

// ── Strategies ────────────────────────────────────────────────────────────────

export interface StrategyConfig {
  name: string
  description: string
  category: string
  enabled: boolean
  interval_seconds: number
  params: Record<string, unknown>
  default_params: Record<string, unknown>
  updated_at: string | null
}

export async function fetchStrategies(): Promise<StrategyConfig[]> {
  const { data } = await adminApi.get('/strategies')
  return data
}

export async function updateStrategy(name: string, body: { enabled?: boolean; interval_seconds?: number; params?: Record<string, unknown> }): Promise<StrategyConfig> {
  const { data } = await adminApi.put(`/strategies/${name}`, body)
  return data
}

export async function runStrategyNow(name: string): Promise<{ status: string }> {
  const { data } = await adminApi.post(`/strategies/${name}/run-now`)
  return data
}

// ── Market Watch ──────────────────────────────────────────────────────────────

export interface MarketWatchRow {
  id: number
  ticker: string
  category: string
  source: string
  enabled: boolean
  created_at: string | null
}

export async function fetchMarketWatches(params?: Record<string, string | number | boolean>): Promise<{ items: MarketWatchRow[]; total: number }> {
  const { data } = await adminApi.get('/markets/watch', { params })
  return data
}

export async function createMarketWatch(body: { ticker: string; category?: string; source?: string; enabled?: boolean }): Promise<MarketWatchRow> {
  const { data } = await adminApi.post('/markets/watch', body)
  return data
}

export async function deleteMarketWatch(id: number): Promise<void> {
  await adminApi.delete(`/markets/watch/${id}`)
}

// ── Decision Log ──────────────────────────────────────────────────────────────

export interface DecisionLogRow {
  id: number
  strategy: string
  market_ticker: string
  decision: string
  confidence: number | null
  reason: string | null
  outcome: string | null
  created_at: string | null
}

export interface DecisionLogDetail extends DecisionLogRow {
  signal_data: Record<string, unknown> | null
}

export async function fetchDecisions(params?: Record<string, string | number>): Promise<{ items: DecisionLogRow[]; total: number }> {
  const { data } = await api.get('/decisions', { params })
  return data
}

export async function fetchDecision(id: number): Promise<DecisionLogDetail> {
  const { data } = await api.get(`/decisions/${id}`)
  return data
}

export function decisionsExportUrl(params?: Record<string, string>): string {
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  return `${API_BASE}/api/decisions/export${qs}`
}

// ── Health ────────────────────────────────────────────────────────────────────

export interface StrategyHealth {
  name: string
  last_heartbeat: string | null
  lag_seconds: number | null
  healthy: boolean
}

export async function fetchHealth(): Promise<{ strategies: StrategyHealth[]; bot_running: boolean }> {
  const { data } = await api.get('/health')
  return data
}

// ── Signal Config (public, no auth) ────────────────────────────────────────────

export interface SignalConfig {
  approval_mode: 'manual' | 'auto_approve' | 'auto_deny'
  min_confidence: number
  notification_duration_ms: number
}

export async function fetchSignalConfig(): Promise<SignalConfig> {
  const { data } = await api.get('/signal-config')
  return data
}

// ── AI Suggest ────────────────────────────────────────────────────────────────

export async function fetchAISuggest(): Promise<{
  status: string
  suggestions: Record<string, unknown>
  analysis: Record<string, unknown>
  ai_provider: string
  raw_response?: string
}> {
  const { data } = await adminApi.get('/admin/ai/suggest')
  return data
}

// ============================================================================
// PE-011 Phase 2 endpoints — auto-trader pending approvals
// ============================================================================

export interface PendingApproval {
  id: number
  market_id: string
  direction: string
  size: number
  confidence: number
  signal_data: Record<string, unknown> | null
  status: string
  created_at: string | null
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  const { data } = await adminApi.get<PendingApproval[]>('/auto-trader/pending')
  return data
}

export async function approvePendingTrade(id: number): Promise<{ id: number; status: string }> {
  const { data } = await adminApi.post<{ id: number; status: string }>(`/auto-trader/approve/${id}`)
  return data
}

export async function rejectPendingTrade(id: number): Promise<{ id: number; status: string }> {
  const { data } = await adminApi.post<{ id: number; status: string }>(`/auto-trader/reject/${id}`)
  return data
}

export async function batchApprovePendingTrades(ids: number[]): Promise<{ approved_count: number; approved_ids: number[] }> {
  const { data } = await adminApi.post<{ approved_count: number; approved_ids: number[] }>('/auto-trader/batch-approve', { trade_ids: ids })
  return data
}

export async function batchRejectPendingTrades(ids: number[]): Promise<{ rejected_count: number; rejected_ids: number[] }> {
  const { data } = await adminApi.post<{ rejected_count: number; rejected_ids: number[] }>('/auto-trader/batch-reject', { trade_ids: ids })
  return data
}

export async function clearAllPendingTrades(): Promise<{ cleared_count: number; cleared_ids: number[] }> {
  const { data } = await adminApi.post<{ cleared_count: number; cleared_ids: number[] }>('/auto-trader/clear-all')
  return data
}

export interface WhaleTx {
  id: number
  tx_hash: string
  wallet: string
  market_id: string | null
  side: string | null
  size_usd: number
  observed_at: string | null
}

export async function fetchWhaleTransactions(limit = 50): Promise<WhaleTx[]> {
  const { data } = await api.get<WhaleTx[]>('/whales/transactions', { params: { limit } })
  return data
}

export interface ArbOpportunity {
  market_id: string
  kind: string
  net_profit: number
  yes_price?: number
  no_price?: number
}

export async function fetchArbitrageOpportunities(): Promise<ArbOpportunity[]> {
  const { data } = await api.get<{ opportunities: ArbOpportunity[] }>('/arbitrage/opportunities')
  return data.opportunities ?? []
}

// ── Strategy P&L ─────────────────────────────────────────────────────────────────

export interface StrategyPnL {
  strategy: string
  total_trades: number
  wins: number
  losses: number
  pending: number
  win_rate: number
  total_pnl: number
  avg_edge: number
  avg_size: number
}

export async function fetchStrategyStats(): Promise<{ strategies: StrategyPnL[] }> {
  const { data } = await api.get('/stats/strategies')
  return data
}

// ── Edge Performance (Parallel Edge Discovery) ───────────────────────────────────

export interface EdgePerformanceTrack {
  track_name: string
  total_signals: number
  signals_executed: number
  winning_trades: number
  win_rate: number
  total_pnl: number
  trade_count: number
  status: string
}

export interface EdgePerformanceResponse {
  tracks: EdgePerformanceTrack[]
  days: number
  since_date: string
}

export async function fetchEdgePerformance(days = 7): Promise<EdgePerformanceResponse> {
  const { data } = await api.get<EdgePerformanceResponse>('/edge-performance', { params: { days } })
  return data
}
