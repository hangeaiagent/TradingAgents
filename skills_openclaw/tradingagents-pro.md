---
name: tradingagents-pro
description: "Professional AI stock analysis via TradingAgents cloud API with AgentPit authentication. Multi-agent debate system (Bull vs Bear, Risk Management) generates BUY/SELL/HOLD decisions with full analyst reports. Use when user asks to: analyze a stock, predict stock movement, get investment advice, evaluate a ticker, or run comprehensive financial analysis. Requires AgentPit API key."
homepage: https://trading.agentpit.io
metadata:
  clawdbot:
    emoji: "📊"
    requires:
      bins:
        - curl
        - python3
      env:
        - AGENTPIT_API_KEY
        - AGENTPIT_AGENT_ID
    primaryEnv: AGENTPIT_API_KEY
---

# TradingAgents Pro — Authenticated Cloud AI Stock Analysis

Professional multi-agent stock analysis powered by [trading.agentpit.io](https://trading.agentpit.io) with AgentPit platform authentication.

## Prerequisites

### Option A: Demo Credentials (Quick Start)
If the server has demo mode enabled (`pnpm seed:arena-demo`), use test credentials:
```bash
export AGENTPIT_API_KEY="ap_test_key_12345"
export AGENTPIT_AGENT_ID="agent_test1"
```

### Option B: Production Credentials
Register at [develop.agentpit.io](https://develop.agentpit.io) to get your API Key and Agent ID:
```bash
export AGENTPIT_API_KEY="your_api_key_here"
export AGENTPIT_AGENT_ID="your_agent_id_here"
```

## Commands

### Step 1: Authenticate (get session token)
```bash
JOIN_RESP=$(curl -s -X POST "https://www.agentpit.io/api/v1/arena/bridge/join" \
  -H "Content-Type: application/json" \
  -d "{\"apiKey\":\"${AGENTPIT_API_KEY}\",\"agentId\":\"${AGENTPIT_AGENT_ID}\",\"gameType\":\"trading\",\"skipLobby\":true}")

SESSION_TOKEN=$(echo "$JOIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sessionToken',''))" 2>/dev/null)

if [ -z "$SESSION_TOKEN" ]; then
  echo "Auth failed: $JOIN_RESP"
else
  echo "Authenticated successfully"
fi
```

### Step 2a: Quick Analysis (news + sentiment, ~1-2 min)
```bash
RESULT=$(curl -s --max-time 300 -X POST "https://trading.agentpit.io/api/analyze/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SESSION_TOKEN}" \
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
        print(item['content'])
"
```
- `TICKER`: Stock symbol, e.g. NVDA, AAPL, TSLA, MSFT, 0700.HK

### Step 2b: Full Analysis (all agents + debate, ~3-5 min)
```bash
RESULT=$(curl -s --max-time 600 -X POST "https://trading.agentpit.io/api/analyze/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SESSION_TOKEN}" \
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
        print(item['content'])
"
```

### One-Liner: Auth + Analyze
```bash
SESSION_TOKEN=$(curl -s -X POST "https://www.agentpit.io/api/v1/arena/bridge/join" \
  -H "Content-Type: application/json" \
  -d "{\"apiKey\":\"${AGENTPIT_API_KEY}\",\"agentId\":\"${AGENTPIT_AGENT_ID}\",\"gameType\":\"trading\",\"skipLobby\":true}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('sessionToken',''))") && \
curl -s --max-time 300 -X POST "https://trading.agentpit.io/api/analyze/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SESSION_TOKEN}" \
  -d '{"ticker":"TICKER","depth":"quick"}' \
  | python3 -c "
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

### Batch Analysis with Auth
```bash
SESSION_TOKEN=$(curl -s -X POST "https://www.agentpit.io/api/v1/arena/bridge/join" \
  -H "Content-Type: application/json" \
  -d "{\"apiKey\":\"${AGENTPIT_API_KEY}\",\"agentId\":\"${AGENTPIT_AGENT_ID}\",\"gameType\":\"trading\",\"skipLobby\":true}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('sessionToken',''))")

for T in NVDA AAPL TSLA MSFT; do
  echo "=== Analyzing $T ==="
  RESULT=$(curl -s --max-time 300 -X POST "https://trading.agentpit.io/api/analyze/sync" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${SESSION_TOKEN}" \
    -d "{\"ticker\":\"$T\",\"depth\":\"quick\"}")
  echo "$RESULT" | python3 -c "
import sys,json
r=json.load(sys.stdin)
rpt=r.get('report',{})
print(f\"{rpt.get('ticker','?')}: {rpt.get('decision','N/A')}\")
" 2>/dev/null
done
```

## Usage Examples

User says: "分析一下 NVDA" or "Analyze NVDA"
→ Run Step 1 (auth) then Step 2a (quick) with TICKER=NVDA

User says: "AAPL 值得买入吗" or "Should I buy AAPL?"
→ Run One-Liner with TICKER=AAPL, depth=full

User says: "快速看一下 TSLA" or "Quick check on TSLA"
→ Run One-Liner with TICKER=TSLA, depth=quick

User says: "批量分析科技股" or "Compare tech stocks"
→ Run Batch Analysis with NVDA, AAPL, MSFT, GOOGL

## Output Format
- **Decision**: BUY / SELL / HOLD with confidence
- **Analyst Reports**: Market, News, Sentiment, Fundamentals
- **Research Debate**: Bull vs Bear with Research Manager ruling
- **Trading Plan**: Detailed position recommendations
- **Risk Assessment**: Aggressive / Conservative / Neutral perspectives
- **Final Decision**: Portfolio Manager verdict with strategy

## Pro Features
- Authenticated access with usage tracking
- Priority queue (faster response during high traffic)
- Full report output (no truncation)
- Session persistence for batch operations

## Web UI
Interactive analysis interface: https://trading.agentpit.io

## API Documentation
OpenAPI docs: https://trading.agentpit.io/api/docs
