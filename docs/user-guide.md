# PolyEdge User Guide

A beginner-friendly guide to understanding and using the PolyEdge trading dashboard. No trading or technical experience required.

---

## What is PolyEdge?

PolyEdge is an **automated trading bot** that trades on **prediction markets** like Polymarket. 

**What are prediction markets?** 
Think of them as betting on real-world events. Instead of betting on sports, you're betting on questions like:
- "Will Bitcoin be above $100,000 on Friday?"
- "Will the temperature in NYC exceed 80°F tomorrow?"
- "Will a certain candidate win an election?"

**What does the bot do?**
The bot analyzes data (weather forecasts, Bitcoin price trends, news) and finds opportunities where the market price seems "wrong." If the bot thinks there's a 70% chance of rain but the market says 50%, that's an opportunity to profit.

---

## Dashboard Overview

When you open the dashboard, you'll see a **top navigation bar** with key numbers. Here's what each means:

### Top Stats Bar

| Term | What It Means | Example |
|------|---------------|---------|
| **Mode** | Whether the bot is using real money or fake money | `PAPER` = fake money (safe testing), `LIVE` = real money |
| **Bank** | Your starting amount of money | $100 = You started with $100 |
| **Equity** | Your current total value (bank + profits - losses) | $112 = You've grown from $100 to $112 |
| **P&L** | Profit and Loss - how much you've made or lost | +$12.50 = You're up $12.50 |
| **Win** | Percentage of trades that made money | 65% = 65 out of 100 trades were winners |
| **Exposure** | How much money is currently "in play" (not settled yet) | $15 = $15 is currently bet on open markets |

### Sync Status (Live/Testnet Only)

When running in `LIVE` or `TESTNET` mode, you'll see a sync status indicator showing when the bot last synchronized with the blockchain:

| Indicator | What It Means |
|-----------|---------------|
| **Last Synced** | Timestamp showing when the bot last checked the blockchain for external trades |
| **Green (< 60s ago)** | Sync is current and healthy |
| **Yellow (60-120s ago)** | Sync is slightly stale but acceptable |
| **Red (> 120s ago)** | Sync is stale, may need manual refresh |
| **Refresh Button** | Manually trigger an immediate sync with the blockchain |

The bot automatically syncs every 30-60 seconds in live mode. External trades (made outside the bot) are automatically imported and displayed in your trade history.

### What the Colors Mean

- **Green** = Good (profit, winning)
- **Red** = Bad (loss, losing)
- **Yellow/Amber** = Caution or in-progress
- **Gray** = Neutral or inactive

---

## Dashboard Tabs

The dashboard has 7 tabs. Click each tab name to see different information:

### 1. Overview Tab

**What it shows:** A summary of everything happening right now.

| Section | What It Means |
|---------|---------------|
| **Equity Chart** | A line graph showing your money over time. Going up = good! |
| **Live Signals** | Current trading opportunities the bot found |
| **Recent Trades** | Your last few trades and whether they won or lost |
| **Weather Panel** | Weather-based trading signals (temperature predictions) |
| **Calibration** | How accurate the bot's predictions have been |

### 2. Trades Tab

**What it shows:** Every trade the bot has made.

| Column | What It Means |
|--------|---------------|
| **Market** | What question/event the trade was about |
| **Direction** | `BUY YES` = betting it will happen, `BUY NO` = betting it won't |
| **Entry** | The price you paid (0.60 = 60 cents) |
| **Size** | How much money you bet |
| **P&L** | Profit/loss from this specific trade |
| **Status** | `OPEN` = waiting for result, `SETTLED` = finished |

### 3. Signals Tab

**What it shows:** Trading opportunities the bot is considering.

| Column | What It Means |
|--------|---------------|
| **Signal** | The trading opportunity description |
| **Edge** | How "wrong" the market seems (higher = better opportunity). 5% edge means the bot thinks it has a 5% advantage |
| **Confidence** | How sure the bot is (0-100%). Higher = more certain |
| **Suggested Size** | How much money the bot recommends betting |
| **Action** | "Simulate" button to test-run the trade |

### 4. Markets Tab

**What it shows:** All available prediction markets you could trade on.

| Column | What It Means |
|--------|---------------|
| **Question** | The actual prediction market question |
| **YES Price** | Cost to bet "yes" (0.65 = 65 cents, implying 65% chance) |
| **NO Price** | Cost to bet "no" (0.35 = 35 cents, implying 35% chance) |
| **Volume** | Total money traded on this market |

**Price tip:** If YES costs 70 cents, the market thinks there's a 70% chance of "yes" happening. If you think the real chance is 85%, that's an opportunity!

### 5. Leaderboard Tab

**What it shows:** Which trading strategies are performing best.

| Column | What It Means |
|--------|---------------|
| **Strategy** | The name of the trading method |
| **Return** | How much profit/loss as a percentage |
| **Win Rate** | Percentage of winning trades |
| **Trades** | Number of trades made |
| **Sharpe** | Risk-adjusted returns (higher = better, 1+ is good) |

### 6. Decisions Tab

**What it shows:** The bot's reasoning for each trade.

This is useful for understanding WHY the bot made a decision. You'll see:
- What data the bot analyzed
- What confidence level it had
- Why it chose to buy or skip

### 7. Performance Tab

**What it shows:** Detailed performance statistics and charts.

| Metric | What It Means |
|--------|---------------|
| **Total Return** | Overall profit/loss percentage since starting |
| **Max Drawdown** | The biggest drop from a peak (lower is better) |
| **Sharpe Ratio** | Risk-adjusted performance. >1 = good, >2 = great |
| **Win Rate** | Percentage of winning trades |

---

## Admin Panel

The Admin panel (click "Admin" in the navigation) lets you configure the bot. Here are the key sections:

### Strategies Tab

Enable or disable trading strategies:

| Strategy | What It Does |
|----------|--------------|
| **BTC Oracle** | Trades Bitcoin price prediction markets using AI analysis |
| **Weather EMOS** | Trades temperature markets using weather forecasts |
| **Copy Trader** | Copies trades from successful "whale" traders |
| **Line Movement Detector** | Catches sudden market price changes (5%+ moves) |
| **General Scanner** | Scans all markets for mispriced opportunities |
| **Bond Scanner** | Looks for low-risk, high-certainty trades |

### Settings Tab

Configure bot behavior. Key settings:

| Setting | What It Means | Recommended |
|---------|---------------|-------------|
| **Trading Mode** | `paper` = fake money, `live` = real money | Start with `paper` |
| **Initial Bankroll** | Starting money amount | $100 for testing |
| **Kelly Fraction** | How aggressive to bet (higher = riskier) | 0.05-0.15 |
| **Daily Loss Limit** | Stop trading if you lose this much in a day | $10-20 |
| **Auto Approve** | Automatically place trades without asking | Keep OFF until comfortable |

### API Keys Tab

Connect external services:

| Key | What It's For |
|-----|---------------|
| **GROQ_API_KEY** | AI analysis (free tier available) |
| **TAVILY_API_KEY** | Web search for news research |
| **POLYMARKET credentials** | Required for live trading |
| **TELEGRAM_BOT_TOKEN** | Get trade alerts on your phone |

### Telegram Tab

Set up mobile notifications:
1. Create a Telegram bot via @BotFather
2. Get your chat ID via @userinfobot
3. Enter both in settings
4. Click "Send Test Message" to verify

---

## Common Trading Terms Explained

| Term | Plain English |
|------|---------------|
| **Edge** | Your advantage over the market. 5% edge = you think you have a 5% better estimate than the market |
| **Confidence** | How sure you (or the bot) is about a prediction. 80% confidence = fairly certain |
| **Position** | An open bet that hasn't settled yet |
| **Settlement** | When the market closes and you find out if you won or lost |
| **Liquidity** | How easy it is to buy/sell. High liquidity = easy trades |
| **Slippage** | The difference between expected and actual price (usually small) |
| **Kelly Criterion** | A formula that calculates optimal bet size based on edge and confidence |
| **Drawdown** | How much your balance dropped from its highest point |
| **Sharpe Ratio** | Returns divided by risk. Higher = better risk-adjusted performance |
| **P&L** | Profit and Loss - your total gains minus losses |
| **ROI** | Return on Investment - profit as a percentage of starting money |

---

## How the Bot Makes Money

1. **Data Analysis**: The bot gathers data (weather forecasts, price trends, news)
2. **Probability Estimate**: It calculates what it thinks the true probability is
3. **Edge Detection**: It compares its estimate to the market price
4. **Trade Decision**: If the edge is big enough (e.g., >5%), it considers trading
5. **Size Calculation**: It uses Kelly Criterion to decide how much to bet
6. **Execution**: It places the trade (or waits for your approval)
7. **Settlement**: When the event happens, you win or lose based on the outcome

**Example:**
- Market question: "Will BTC be above $100K on Friday?"
- Market price: 60 cents (implies 60% chance)
- Bot's estimate: 75% chance based on momentum analysis
- Edge: 75% - 60% = 15% edge
- Action: Buy YES at 60 cents
- If BTC is above $100K: You get $1.00 back (40 cent profit)
- If BTC is below $100K: You lose your 60 cents

---

## Safety Tips for Beginners

1. **Start with Paper Mode**: Always test with fake money first
2. **Small Bankroll**: When going live, start with $25-50 you can afford to lose
3. **Set Loss Limits**: Configure daily loss limits to prevent big losses
4. **Manual Approval**: Keep auto-approve OFF and review each trade
5. **Understand Before Trading**: Read the bot's reasoning in the Decisions tab
6. **Check Calibration**: A well-calibrated bot should be right about as often as its confidence suggests
7. **Diversify**: Don't put all your money on one strategy or market

---

## Troubleshooting

### "No signals appearing"
- Check that strategies are enabled in Admin > Strategies
- Verify API keys are configured in Admin > Settings > API Keys
- The bot scans periodically (every 1-5 minutes depending on strategy)

### "Trades not executing"
- Check Trading Mode is set correctly (paper vs live)
- Verify Polymarket credentials are configured for live trading
- Check if Daily Loss Limit has been hit

### "Dashboard not updating"
- Refresh the page
- Check the WebSocket indicator (top right) - should show "Connected"
- Verify backend is running (check system status in Admin)

### "Sync status shows stale or red"
- Click the manual refresh button next to the sync timestamp
- Check that you're in LIVE or TESTNET mode (paper mode doesn't sync)
- Verify your Polymarket API credentials are configured correctly
- Check backend logs for sync errors

### "Telegram alerts not working"
- Verify TELEGRAM_BOT_TOKEN is set
- Verify TELEGRAM_ADMIN_CHAT_IDS contains your chat ID
- Check TELEGRAM_HIGH_CONFIDENCE_ALERTS is enabled
- Use the "Send Test Message" button in Admin > Telegram

---

## Quick Start Checklist

- [ ] Open dashboard at your deployed URL
- [ ] Check you're in PAPER mode (top left shows "PAPER")
- [ ] Go to Admin > Strategies and enable 1-2 strategies
- [ ] Go to Admin > Settings and verify API keys are set
- [ ] Return to Dashboard > Overview
- [ ] Wait for signals to appear (may take a few minutes)
- [ ] Review signals in Signals tab
- [ ] Click "Simulate" to test a trade
- [ ] Monitor trades in Trades tab
- [ ] Check performance in Performance tab

Once comfortable with paper trading, you can switch to live mode with real money.

---

## Getting Help

- **Dashboard Issues**: Check Admin > System Status for errors
- **Strategy Questions**: Review the Decisions tab for bot reasoning
- **Technical Issues**: Check PM2 logs on the server
- **General Questions**: Refer to this guide or the technical documentation

Remember: Prediction markets involve risk. Never trade with money you can't afford to lose.
