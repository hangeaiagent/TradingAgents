# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a multi-agent LLM-based financial trading framework that mirrors real-world trading firms. Specialized agents (analysts, researchers, traders, risk managers) collaborate via LangGraph to produce trading decisions. Python 3.10+ required.

## Setup & Development Commands

```bash
# Install dependencies
pip install -r requirements.txt
# Or install as package
pip install -e .

# Run CLI (interactive mode)
python -m cli.main

# Run basic test/example
python test.py

# Run programmatically
python main.py
```

No formal test framework, linter, or CI/CD is configured. There is no Makefile.

## Required Environment Variables

Copy `.env.example` to `.env`. At minimum one LLM provider key is needed:
- `OPENAI_API_KEY` — for OpenAI models
- `GOOGLE_API_KEY` — for Gemini models
- `ANTHROPIC_API_KEY` — for Claude models
- `XAI_API_KEY` — for Grok models

## Architecture

### Execution Flow (LangGraph)

```
TradingAgentsGraph.propagate(ticker, date)
  → Analyst Stage (parallel): Market, Sentiment, News, Fundamentals
  → Investment Debate (sequential): Bull Researcher ↔ Bear Researcher → Research Manager
  → Trader: produces investment plan
  → Risk Debate (sequential): Aggressive/Conservative/Neutral debators → Risk Manager
  → Portfolio Manager: final trade decision (BUY/SELL/HOLD)
```

### Key Modules

- **`tradingagents/graph/`** — LangGraph orchestration. `TradingAgentsGraph` in `trading_graph.py` is the main entry point. `setup.py` builds the graph workflow, `conditional_logic.py` handles routing (debate continuation), `propagation.py` creates initial state, `reflection.py` handles learning from outcomes.

- **`tradingagents/agents/`** — All agent implementations. Each agent is a function that takes state and returns updated state. Agent state types (`AgentState`, `InvestDebateState`, `RiskDebateState`) are TypedDicts in `agents/utils/agent_states.py`.

- **`tradingagents/dataflows/`** — Pluggable data vendor system. `interface.py` routes tool calls to configured vendor (yfinance or Alpha Vantage). Supports category-level and tool-level vendor overrides with automatic fallback on rate limits. yfinance is the default (no API key needed).

- **`tradingagents/llm_clients/`** — Multi-provider LLM factory. `create_llm_client(provider, model, ...)` returns a LangChain chat model. Supports: openai, anthropic, google, xai, ollama, openrouter.

- **`tradingagents/default_config.py`** — Central configuration dict. Controls LLM provider/model selection, debate rounds, data vendors, result directories.

- **`tradingagents/agents/utils/memory.py`** — `FinancialSituationMemory` uses BM25 lexical similarity (no embedding API calls). Used by researchers, trader, and managers to recall past situations.

- **`cli/`** — Typer-based CLI with Rich TUI. `cli/main.py` is the main entry (~1500 lines). `cli/stats_handler.py` tracks agent execution progress.

### Configuration Pattern

```python
from tradingagents.default_config import DEFAULT_CONFIG
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # or google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"    # Complex reasoning
config["quick_think_llm"] = "gpt-5-mini" # Quick tasks
config["max_debate_rounds"] = 2
config["max_risk_discuss_rounds"] = 1
config["data_vendors"] = {"core_stock_apis": "yfinance", ...}
config["tool_vendors"] = {"get_stock_data": "alpha_vantage"}  # per-tool override
```

### Dependencies

Core: LangChain + LangGraph for orchestration, yfinance + stockstats for market data, Typer + Rich for CLI, rank-bm25 for memory similarity, backtrader for backtesting.
