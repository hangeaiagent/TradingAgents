---
name: tradingagents
description: "AI-powered multi-agent stock analysis using TradingAgents framework. Analyzes fundamentals, market sentiment, news impact, and technical indicators to generate trading decisions. Use this when user asks to: analyze a stock, predict stock movement, get investment advice, check if a stock is worth buying, analyze market sentiment for a ticker, or get a comprehensive financial report on any public company."
homepage: https://github.com/agentpit/tradingagents-skill
metadata:
  clawdbot:
    emoji: "📈"
    requires:
      bins:
        - python3
      env:
        - OPENAI_API_KEY
    primaryEnv: OPENAI_API_KEY
---

# TradingAgents — Multi-Agent Stock Analysis

Comprehensive AI-powered stock analysis using a team of specialized agents that mirror a real trading firm.

## Agents Involved
- **Fundamentals Analyst**: Evaluates company financials, earnings, PE ratios
- **Sentiment Analyst**: Analyzes social media and public sentiment
- **News Analyst**: Interprets macro events and their market impact
- **Technical Analyst**: RSI, EMA, MACD, momentum signals
- **Risk Manager + Trader**: Synthesizes all inputs into a final decision

## Commands

### Full Analysis (recommended)
```bash
{baseDir}/scripts/run.sh --ticker TICKER --date DATE --depth full
```
- `TICKER`: Stock symbol, e.g. NVDA, AAPL, TSLA, 0700.HK
- `DATE`: Analysis date in YYYY-MM-DD format (default: today)
- `--depth full`: Runs all 4 analyst agents + debate + decision (takes 2-3 min)

### Quick Analysis (news + sentiment only)
```bash
{baseDir}/scripts/run.sh --ticker TICKER --date DATE --depth quick
```
- `--depth quick`: Runs only news + sentiment agents (takes ~30 sec)

### Batch Analysis
```bash
{baseDir}/scripts/run.sh --tickers "NVDA,AAPL,TSLA" --date DATE --depth quick
```

## Usage Examples

User says: "分析一下 NVDA" or "Analyze NVDA"
→ Run: `{baseDir}/scripts/run.sh --ticker NVDA --depth full`

User says: "AAPL 值得买入吗" or "Should I buy AAPL?"
→ Run: `{baseDir}/scripts/run.sh --ticker AAPL --depth full`

User says: "快速看一下 TSLA 的情绪" or "Quick sentiment check on TSLA"
→ Run: `{baseDir}/scripts/run.sh --ticker TSLA --depth quick`

User says: "批量分析科技股" or "Analyze big tech stocks"
→ Run: `{baseDir}/scripts/run.sh --tickers "NVDA,AAPL,MSFT,GOOGL" --depth quick`

## Output Format
The script outputs a structured analysis report:
- Summary decision (BUY / HOLD / SELL)
- Technical signals
- Key news impact
- Market sentiment
- Risk factors
- Key catalysts to watch

## Prerequisites
Set these in OpenClaw config or environment:
- `OPENAI_API_KEY`: Required (or set `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`)
- Optional: `ALPHA_VANTAGE_API_KEY` for alternative market data source

## LLM Provider Config (optional)
By default uses OpenAI. To use Claude:
```bash
{baseDir}/scripts/run.sh --ticker NVDA --llm anthropic --model claude-sonnet-4-6
```
To use Gemini:
```bash
{baseDir}/scripts/run.sh --ticker NVDA --llm google --model gemini-3.1-pro
```
