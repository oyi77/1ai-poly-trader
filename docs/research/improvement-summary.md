# Improvement Research & External Reference Index

> **Purpose:** Catalog of external repos, libraries, datasets, and concepts discovered during research that could improve PolyEdge. 
> **Updated:** 2026-05-18
> 
> Use this file to track promising leads without committing to immediate implementation. When an AGI sprint starts, check here first.

---

## 🥇 Tier 1 — Integrate Directly

### 1. PMXT — CCXT for Prediction Markets
| Field | Value |
|---|---|
| **Repo** | https://github.com/pmxt-dev/pmxt |
| **Stars** | 1,736⭐ |
| **Language** | Python + TypeScript |
| **Value** | 🔴 **Replace CLOB client** — single API for Polymarket, Kalshi, Limitless, Hyperliquid |
| **Install** | `pip install pmxt` |
| **Why** | Our `polymarket_clob.py` only handles Polymarket. PMXT supports 10+ platforms with unified interface. Also has MCP server (`npx @pmxt/mcp`). |
| **ROI** | High — eliminates need for separate Kalshi/Limitless connectors |

### 2. Polymarket Strategy Backtester
| Field | Value |
|---|---|
| **Repo** | https://github.com/Polymarket-Research/Polymarket-Strategy-Backtester |
| **Stars** | 596⭐ |
| **Value** | 🟡 **Backtest validation** — compare our backtest results against theirs |
| **Why** | Dedicated Polymarket backtesting engine. Can validate our backtest accuracy. |

### 3. Polymarket Paper Trader
| Field | Value |
|---|---|
| **Repo** | https://github.com/agent-next/polymarket-paper-trader |
| **Stars** | 330⭐ |
| **Value** | 🔴 **Replace paper mode** — real order book execution, exact fee model |
| **Install** | `pip install polymarket-paper-trader` or `npx clawhub install polymarket-paper-trader` |
| **Why** | Our paper mode fabricates fills. This uses real Polymarket order books, level-by-level execution, slippage tracking. MCP server included for AGI integration. |

---

## 🥈 Tier 2 — Architecture Reference

### 4. Polymarket/agents (Official)
| Field | Value |
|---|---|
| **Repo** | https://github.com/Polymarket/agents |
| **Stars** | 3,505⭐ |
| **Value** | 🟡 **RAG pipeline, news sourcing, LLM tools** |
| **Why** | Official Polymarket framework for AI agents. Their RAG pipeline + news sourcing architecture can be adopted. |

### 5. rqalpha
| Field | Value |
|---|---|
| **Repo** | https://github.com/ricequant/rqalpha |
| **Stars** | 6,391⭐ |
| **Value** | 🟢 **Event-driven architecture, portfolio management** |
| **Why** | Battle-tested backtesting framework (6k+ stars). Event-driven pattern can improve our architecture. |

### 6. lumibot
| Field | Value |
|---|---|
| **Repo** | https://github.com/Lumiwealth/lumibot |
| **Stars** | 1,555⭐ |
| **Value** | 🟢 **Broker abstraction, strategy lifecycle** |
| **Why** | AI trading agents framework. Good reference for strategy lifecycle patterns. |

---

## 🥉 Tier 3 — Concepts to Learn

### 7. PyBroker
| Field | Value |
|---|---|
| **Repo** | https://github.com/edtechre/pybroker |
| **Stars** | 2,100⭐ |
| **Value** | 🟢 **NumPy-accelerated backtesting, Walkforward Analysis** |
| **Key Concepts** | Bootstrap metrics, custom data sources, model-based strategies |

### 8. polybot
| Field | Value |
|---|---|
| **Repo** | https://github.com/poly-bot/polybot |
| **Stars** | 636⭐ |
| **Value** | 🔵 **Whale detection, copy trading signals** |
| **Why** | Reverse-engineers Polymarket strategies. Could help with copy-trader module. |

### 9. OctoBot
| Field | Value |
|---|---|
| **Repo** | https://github.com/Drakkar-Software/OctoBot |
| **Stars** | 6,800⭐ |
| **Value** | 🔵 **Exchange abstraction, deployment patterns** |
| **Key Concepts** | 15+ exchange integration via CCXT, Docker deployment, mobile app |

### 10. OpenAlice
| Field | Value |
|---|---|
| **Repo** | https://github.com/TraderAlice/OpenAlice |
| **Stars** | New |
| **Value** | 🔵 **Trade-as-Git concept, Guard pipeline** |
| **Key Concepts** | Stage → Commit → Push execution, pre-execution safety checks, multi-broker UTA |

### 11. basana
| Field | Value |
|---|---|
| **Repo** | https://github.com/vmleon/basana |
| **Stars** | 829⭐ |
| **Value** | 🔵 **Async event-driven framework** |
| **Key Concepts** | Event bus patterns for async strategy execution |

### 12. Polymarket MCP Server
| Field | Value |
|---|---|
| **Repo** | https://github.com/Polymarket/polymarket-mcp-server |
| **Stars** | ~500⭐ |
| **Value** | 🔵 **MCP integration for Polymarket** |
| **Install** | Already installed (polymarket-mcp package) |

### 13. polymarket-paper-trader (by jchimbor)
| Field | Value |
|---|---|
| **Repo** | https://github.com/jchimbor/polymarket-paper-trader |
| **Stars** | 1⭐ |
| **Value** | 🔵 Alternative paper trader with real order books |

---

## 📊 Datasets for AGI Training

Found via GitHub API search — datasets that can make our AGI smarter over time:

| Dataset | Stars | Description | Use for AGI |
|---|---|---|---|
| **Polymarket_data** | 566⭐ | 1.1 billion trading records from Polymarket | 🔴 **Training data for market prediction models** |
| **prediction-market-analysis** | 3,369⭐ | Framework for collecting/analyzing prediction market data | 🟡 **Feature engineering pipeline** |
| **PolymarketBTC15mAssistant** | 692⭐ | Real-time BTC 15m trading assistant data | 🟡 **Pattern recognition training** |
| **Dome API (pmxt alternative)** | — | Prediction market data API | 🟢 **Alternative data source** |

**Kaggle / External Datasets to Explore:**
- Polymarket trade history (available via Data API)
- Kalshi event resolution history
- CoinGecko crypto price history (for oracle strategies)
- NOAA weather data (for weather markets settlement)

---

## 🎯 Priority Implementation Roadmap

```
Phase 1 (Now — May 2026):
  □ Replace paper mode with polymarket-paper-trader (MCP-based)
  □ Validate backtest accuracy against Polymarket Strategy Backtester

Phase 2 (Next — June 2026):
  □ Evaluate PMXT integration (replace CLOB client)
  □ Adopt Polymarket/agents RAG pipeline
  □ Integrate Polymarket_data dataset for ML training

Phase 3 (Future):
  □ PyBroker backtesting integration
  □ Architecture refactor using rqalpha/lumibot patterns
  □ OctoBot-style deployment pipeline
```
