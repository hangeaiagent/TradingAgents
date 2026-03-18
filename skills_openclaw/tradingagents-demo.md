---
name: tradingagents-demo
description: "Free AI stock analysis demo via TradingAgents cloud API (trading.agentpit.io). Analyzes news, sentiment, fundamentals, and technicals using multi-agent debate to generate BUY/SELL/HOLD decisions. Use when user asks to: analyze a stock, get trading advice, check market sentiment, or evaluate if a stock is worth buying. No API keys needed — uses shared demo instance."
homepage: https://trading.agentpit.io
metadata:
  clawdbot:
    emoji: "📈"
    requires:
      bins:
        - curl
        - python3
    primaryEnv: NONE
---

# TradingAgents Demo — Cloud AI Stock Analysis

Free multi-agent stock analysis powered by [trading.agentpit.io](https://trading.agentpit.io).
No API keys required — uses the shared cloud instance.

## How It Works
A team of AI agents collaborates to analyze stocks:
- **News Analyst** + **Sentiment Analyst**: Market news and public sentiment
- **Market Analyst** + **Fundamentals Analyst**: Technical indicators and financials (full mode)
- **Bull vs Bear Debate**: Researchers argue both sides
- **Risk Management**: Aggressive/Conservative/Neutral views
- **Final Decision**: Portfolio Manager delivers BUY / SELL / HOLD

## Commands

### Quick Analysis (news + sentiment, ~1-2 min)
```bash
RESULT=$(curl -s --max-time 300 -X POST "https://trading.agentpit.io/api/analyze/sync" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TICKER","depth":"quick"}')
echo "$RESULT" | python3 -c "
import sys,json
r=json.load(sys.stdin)
if r.get('status')=='error': print('Error:',r['message']); sys.exit(1)
rpt=r['report']
print(f\"# {rpt['ticker']} ({rpt['date']}) — Decision: {rpt['decision']}\")
for s in rpt['sections']:
    print(f\"\n## {s['title']}\")
    for item in s['items']:
        print(f\"\n### {item['name']}\")
        print(item['content'][:2000])
"
```
- `TICKER`: Stock symbol, e.g. NVDA, AAPL, TSLA, MSFT

### Full Analysis (all agents + debate, ~3-5 min)
```bash
RESULT=$(curl -s --max-time 600 -X POST "https://trading.agentpit.io/api/analyze/sync" \
  -H "Content-Type: application/json" \
  -d '{"ticker":"TICKER","depth":"full"}')
echo "$RESULT" | python3 -c "
import sys,json
r=json.load(sys.stdin)
if r.get('status')=='error': print('Error:',r['message']); sys.exit(1)
rpt=r['report']
print(f\"# {rpt['ticker']} ({rpt['date']}) — Decision: {rpt['decision']}\")
for s in rpt['sections']:
    print(f\"\n## {s['title']}\")
    for item in s['items']:
        print(f\"\n### {item['name']}\")
        print(item['content'][:2000])
"
```

### Batch Quick Analysis
```bash
for T in NVDA AAPL TSLA MSFT; do
  echo "=== Analyzing $T ==="
  RESULT=$(curl -s --max-time 300 -X POST "https://trading.agentpit.io/api/analyze/sync" \
    -H "Content-Type: application/json" \
    -d "{\"ticker\":\"$T\",\"depth\":\"quick\"}")
  DECISION=$(echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['report']['decision'])" 2>/dev/null)
  echo "$T: $DECISION"
done
```

## Usage Examples

User says: "分析一下 NVDA" or "Analyze NVDA"
→ Run Quick Analysis with TICKER=NVDA

User says: "AAPL 值得买入吗" or "Should I buy AAPL?"
→ Run Full Analysis with TICKER=AAPL

User says: "快速看一下 TSLA" or "Quick check on TSLA"
→ Run Quick Analysis with TICKER=TSLA

User says: "批量分析科技股" or "Compare big tech stocks"
→ Run Batch Quick Analysis with NVDA, AAPL, MSFT, GOOGL

## Output
- **Decision**: BUY / SELL / HOLD
- **Analyst Reports**: News, Sentiment, Technical, Fundamentals
- **Research Debate**: Bull vs Bear arguments
- **Risk Assessment**: Aggressive / Conservative / Neutral views
- **Final Recommendation**: Portfolio Manager decision with rationale

## Limitations (Demo)
- Shared cloud instance — may queue during high traffic
- Rate limited to prevent abuse
- For production use, deploy your own instance or use the Pro skill

## Web UI
You can also use the interactive web interface at: https://trading.agentpit.io
