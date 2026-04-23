import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

const strategies = [
  {
    id: 'copy_trader',
    title: 'Copy Trader',
    badge: 'CT',
    badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    status: 'live',
    description: 'Mirrors top-scored Polymarket wallets with proportional sizing. Tracks 50% exit signals and manages positions automatically.',
  },
  {
    id: 'weather_emos',
    title: 'Weather EMOS',
    badge: 'WX',
    badgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    status: 'live',
    description: 'GEFS ensemble forecasts with 31 members, Welford online calibration, and probabilistic edge detection across 11 global cities.',
  },
  {
    id: 'kalshi_arb',
    title: 'Kalshi Arb',
    badge: 'KA',
    badgeColor: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    status: 'configurable',
    description: 'Cross-exchange arbitrage between Kalshi and Polymarket. Exploits pricing inefficiencies on correlated prediction markets.',
  },
  {
    id: 'btc_oracle',
    title: 'BTC Oracle',
    badge: 'BO',
    badgeColor: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    status: 'configurable',
    description: 'BTC price oracle latency arbitrage using CoinGecko free API. Trades ahead of slow market updates on Polymarket BTC price markets.',
  },
  {
    id: 'btc_5m',
    title: 'BTC 5-Minute',
    badge: 'B5',
    badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    status: 'experimental',
    description: 'RSI, momentum, and VWAP signals on 5-minute BTC windows. Composite edge scoring with Kelly criterion sizing.',
  },
]

const modes = [
  {
    label: 'Paper',
    color: 'text-neutral-400 border-neutral-600',
    dot: 'bg-neutral-500',
    description: 'Simulate trades with no credentials. Full PNL tracking against virtual bankroll.',
  },
  {
    label: 'Testnet',
    color: 'text-yellow-400 border-yellow-700',
    dot: 'bg-yellow-500',
    description: 'Amoy testnet (chain 80002) with real CLOB execution. Requires private key only.',
  },
  {
    label: 'Live',
    color: 'text-red-400 border-red-700',
    dot: 'bg-red-500',
    description: 'Full mainnet Polymarket CLOB with EIP-712 signing. Requires API key, secret, and passphrase.',
  },
]

const capabilities = [
  {
    icon: '◈',
    title: 'Decision Log',
    description: 'Every BUY/SKIP/SELL/HOLD recorded with signal data, outcome, and edge score. Exportable as JSONL for ML training.',
  },
  {
    icon: '◉',
    title: 'Real-Time Events',
    description: 'SSE push notifications for trade opens, settlements, and signal detections — styled by tier size like aggr.trade.',
  },
  {
    icon: '◎',
    title: 'Whale Tracker',
    description: 'Leaderboard of top Polymarket wallets scored by 30-day profit, win rate, and trade volume.',
  },
  {
    icon: '◆',
    title: 'Market Intelligence',
    description: 'Per-strategy health monitoring, live enable/disable toggles, and market watch configuration.',
  },
  {
    icon: '◇',
    title: 'Kelly Sizing',
    description: 'Fractional Kelly criterion with daily loss limits, max position caps, and configurable risk per trade.',
  },
  {
    icon: '◐',
    title: 'Admin Panel',
    description: '8-tab control center: Settings, System status, Copy Trader config, Telegram alerts, Credentials, Strategies, Market Watch, Wallet Config.',
  },
]

const steps = [
  {
    step: '01',
    title: 'Scan',
    description: 'Continuous scanning across all ~2,000 active Polymarket markets plus Kalshi. Each strategy independently identifies its target market types.',
  },
  {
    step: '02',
    title: 'Signal',
    description: 'Composite signal generation: RSI, momentum, VWAP, ensemble weather forecasts, oracle latency, copy wallet tracking. Edge and confidence scored.',
  },
  {
    step: '03',
    title: 'Decide',
    description: 'BUY/SKIP/SELL/HOLD decision logged with full signal data, confidence, and rationale. Every skip is tracked for post-analysis.',
  },
  {
    step: '04',
    title: 'Execute',
    description: 'Automated trade execution via Polymarket CLOB API. EIP-712 signing, fractional Kelly sizing, daily loss limits enforced.',
  },
  {
    step: '05',
    title: 'Settle',
    description: 'Automatic settlement detection. PNL realized, win/loss recorded, decision log outcome backfilled, equity curve updated.',
  },
]

const navLinks = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/whale-tracker', label: 'Whales' },
  { to: '/market-intel', label: 'Intel' },
  { to: '/decisions', label: 'Decisions' },
  { to: '/settlements', label: 'Settlements' },
  { to: '/admin', label: 'Admin' },
  { to: '/docs/', label: 'Docs', external: true },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-black text-neutral-200 font-mono">
      {/* Nav */}
      <nav className="border-b border-neutral-800 px-4 sm:px-6 py-3 flex items-center gap-3 sticky top-0 bg-black/95 z-10 backdrop-blur overflow-x-auto scrollbar-none">
        <span className="text-xs font-bold text-neutral-100 uppercase tracking-[0.3em] shrink-0">PolyEdge</span>
        <div className="flex items-center gap-3 sm:gap-4">
          {navLinks.map(l => (
            l.external ? (
              <a
                key={l.to}
                href={l.to}
                className="text-[10px] text-neutral-500 hover:text-green-500 uppercase tracking-wider transition-colors whitespace-nowrap"
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.to}
                to={l.to}
                className="text-[10px] text-neutral-500 hover:text-green-500 uppercase tracking-wider transition-colors whitespace-nowrap"
              >
                {l.label}
              </Link>
            )
          ))}
        </div>
      </nav>

      {/* Hero */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="px-6 py-20 max-w-4xl mx-auto text-center"
      >
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="px-2 py-1 text-[9px] font-bold uppercase bg-green-500/10 text-green-500 border border-green-500/20 tracking-wider">
            v3.0
          </span>
          <span className="px-2 py-1 text-[9px] font-bold uppercase bg-purple-500/10 text-purple-400 border border-purple-500/20 tracking-wider">
            5 Strategies
          </span>
          <span className="px-2 py-1 text-[9px] font-bold uppercase bg-amber-500/10 text-amber-400 border border-amber-500/20 tracking-wider">
            Paper · Testnet · Live
          </span>
        </div>

        <h1 className="text-4xl font-bold text-neutral-100 uppercase tracking-widest mb-4">
          PolyEdge
        </h1>
        <p className="text-lg text-green-500 uppercase tracking-wider mb-3">
          Autonomous Prediction Market Trading
        </p>
        <p className="text-sm text-neutral-500 max-w-2xl mx-auto leading-relaxed mb-10">
          Five independent alpha strategies running 24/7 on Polymarket and Kalshi.
          Every trade decision logged, every edge quantified, full Kelly sizing with
          real-time SSE push notifications.
        </p>

        <div className="flex items-center justify-center gap-3 flex-wrap">
          <Link
            to="/dashboard"
            className="px-6 py-2.5 bg-green-500/10 border border-green-500/30 text-green-400 text-xs uppercase tracking-wider hover:bg-green-500/20 transition-colors"
          >
            Live Dashboard
          </Link>
          <Link
            to="/decisions"
            className="px-6 py-2.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider hover:border-neutral-500 transition-colors"
          >
            Decision Log
          </Link>
          <Link
            to="/admin"
            className="px-6 py-2.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider hover:border-neutral-500 transition-colors"
          >
            Admin Panel
          </Link>
        </div>
      </motion.section>

      {/* Trading Modes */}
      <section className="px-6 py-12 max-w-5xl mx-auto border-t border-neutral-800">
        <div className="text-center mb-8">
          <span className="text-[10px] text-neutral-600 uppercase tracking-[0.3em]">Trading Modes</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {modes.map((m, i) => (
            <motion.div
              key={m.label}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="border border-neutral-800 bg-neutral-900/20 p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
                <span className={`text-xs font-bold uppercase tracking-wider border px-1.5 py-0.5 ${m.color}`}>
                  {m.label}
                </span>
              </div>
              <p className="text-[11px] text-neutral-500 leading-relaxed">{m.description}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Strategies */}
      <section className="px-6 py-12 max-w-5xl mx-auto border-t border-neutral-800">
        <div className="text-center mb-8">
          <span className="text-[10px] text-neutral-600 uppercase tracking-[0.3em]">5 Alpha Strategies</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((s, i) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * 0.07 }}
              className="border border-neutral-800 bg-neutral-900/30 p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={`px-1.5 py-0.5 text-[8px] font-bold uppercase border ${s.badgeColor}`}>
                  {s.badge}
                </span>
                <h3 className="text-xs font-bold text-neutral-200 uppercase tracking-wider flex-1">{s.title}</h3>
                <span className={`text-[8px] uppercase tracking-wider ${
                  s.status === 'live' ? 'text-green-500' :
                  s.status === 'experimental' ? 'text-red-400' : 'text-neutral-600'
                }`}>
                  {s.status}
                </span>
              </div>
              <p className="text-[11px] text-neutral-500 leading-relaxed">{s.description}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Capabilities */}
      <section className="px-6 py-12 max-w-5xl mx-auto border-t border-neutral-800">
        <div className="text-center mb-8">
          <span className="text-[10px] text-neutral-600 uppercase tracking-[0.3em]">Platform</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {capabilities.map((c, i) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
              className="flex gap-3 p-4 border border-neutral-800/60 bg-neutral-900/10"
            >
              <span className="text-green-500/60 text-sm shrink-0 mt-0.5">{c.icon}</span>
              <div>
                <h4 className="text-[11px] font-bold text-neutral-300 uppercase tracking-wider mb-1">{c.title}</h4>
                <p className="text-[10px] text-neutral-600 leading-relaxed">{c.description}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Pipeline */}
      <section className="px-6 py-12 max-w-5xl mx-auto border-t border-neutral-800">
        <div className="text-center mb-10">
          <span className="text-[10px] text-neutral-600 uppercase tracking-[0.3em]">Trade Pipeline</span>
        </div>
        <div className="relative">
          {/* connector line */}
          <div className="hidden md:block absolute top-4 left-[10%] right-[10%] h-px bg-neutral-800" />
          <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
            {steps.map((s, i) => (
              <motion.div
                key={s.step}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.3 + i * 0.08 }}
                className="text-center relative"
              >
                <div className="text-2xl font-bold text-neutral-800 mb-2 tabular-nums">{s.step}</div>
                <h4 className="text-[10px] font-bold text-green-500 uppercase tracking-wider mb-1">{s.title}</h4>
                <p className="text-[10px] text-neutral-600 leading-relaxed">{s.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-16 max-w-2xl mx-auto text-center border-t border-neutral-800">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          <p className="text-[10px] text-neutral-700 uppercase tracking-[0.3em] mb-4">Get Started</p>
          <p className="text-xs text-neutral-500 mb-6 leading-relaxed">
            Start with paper trading — no credentials required. Configure strategies,
            review the decision log, and switch to live when ready.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              to="/dashboard"
              className="px-8 py-2.5 bg-green-500/10 border border-green-500/30 text-green-400 text-xs uppercase tracking-wider hover:bg-green-500/20 transition-colors"
            >
              Open Dashboard
            </Link>
            <Link
              to="/whale-tracker"
              className="px-8 py-2.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider hover:border-neutral-500 transition-colors"
            >
              View Whales
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-neutral-800 px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <span className="text-[10px] text-neutral-700 whitespace-nowrap">
          Polymarket · Kalshi · Binance · Coinbase · Open-Meteo
        </span>
        <div className="flex items-center gap-3 overflow-x-auto scrollbar-none">
          <div className="flex items-center gap-3">
            {navLinks.map(l => (
              l.external ? (
                <a key={l.to} href={l.to} className="text-[9px] text-neutral-700 hover:text-neutral-500 uppercase transition-colors whitespace-nowrap">
                  {l.label}
                </a>
              ) : (
                <Link key={l.to} to={l.to} className="text-[9px] text-neutral-700 hover:text-neutral-500 uppercase transition-colors whitespace-nowrap">
                  {l.label}
                </Link>
              )
            ))}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span className="text-[10px] text-neutral-600 whitespace-nowrap">v3.0.0</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
