"""TradingAgents Web API — FastAPI backend for trading.agentpit.io"""

import os
import sys
import json
import asyncio
import traceback
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ONE_API_KEY → OPENAI_API_KEY fallback
if os.environ.get("ONE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["ONE_API_KEY"]

app = FastAPI(title="TradingAgents", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Serve skill files from project root
SKILLS_DIR = PROJECT_ROOT


class AnalysisRequest(BaseModel):
    ticker: str
    trade_date: Optional[str] = None
    depth: str = "full"  # full or quick
    llm_provider: str = "openai"
    model: Optional[str] = None


def build_config(req: AnalysisRequest):
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = req.llm_provider

    if req.model:
        config["deep_think_llm"] = req.model
        config["quick_think_llm"] = req.model
    elif os.environ.get("ONE_API_GEMINI_MODEL"):
        config["deep_think_llm"] = os.environ["ONE_API_GEMINI_MODEL"]
        config["quick_think_llm"] = os.environ["ONE_API_GEMINI_MODEL"]

    if os.environ.get("ONE_API_BASE_URL"):
        config["backend_url"] = os.environ["ONE_API_BASE_URL"]

    return config


def get_analysts(depth: str):
    if depth == "quick":
        return ["news", "social"]
    return ["market", "social", "news", "fundamentals"]


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/skills/{skill_name}.md")
async def get_skill(skill_name: str):
    """Serve skill markdown files for OpenClaw installation."""
    safe_name = skill_name.replace("..", "").replace("/", "")
    skill_path = SKILLS_DIR / f"skills_openclaw" / f"{safe_name}.md"
    if not skill_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "skill not found"}, status_code=404)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(skill_path.read_text(encoding="utf-8"))


@app.post("/api/analyze/sync")
async def analyze_sync(req: AnalysisRequest):
    """Synchronous analysis endpoint — returns full JSON result (for curl/OpenClaw)."""
    trade_date = req.trade_date or date.today().strftime("%Y-%m-%d")

    try:
        config = build_config(req)
        analysts = get_analysts(req.depth)

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        def run_analysis():
            ta = TradingAgentsGraph(
                selected_analysts=analysts, debug=False, config=config
            )
            return ta.propagate(req.ticker, trade_date)

        loop = asyncio.get_event_loop()
        final_state, decision = await loop.run_in_executor(None, run_analysis)

        report = build_report(final_state, decision, req.ticker, trade_date)
        return {"status": "ok", "report": report, "decision": decision}

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@app.post("/api/analyze")
async def analyze(req: AnalysisRequest):
    """Run analysis and stream results via SSE."""
    trade_date = req.trade_date or date.today().strftime("%Y-%m-%d")

    async def event_stream():
        yield f"data: {json.dumps({'type': 'status', 'message': f'Initializing analysis for {req.ticker}...'})}\n\n"

        try:
            config = build_config(req)
            analysts = get_analysts(req.depth)

            yield f"data: {json.dumps({'type': 'status', 'message': f'Running {req.depth} analysis ({len(analysts)} agents)...'})}\n\n"

            # Run in thread to not block event loop
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            def run_analysis():
                ta = TradingAgentsGraph(
                    selected_analysts=analysts, debug=False, config=config
                )
                return ta.propagate(req.ticker, trade_date)

            loop = asyncio.get_event_loop()
            final_state, decision = await loop.run_in_executor(None, run_analysis)

            # Build report sections
            report = build_report(final_state, decision, req.ticker, trade_date)

            yield f"data: {json.dumps({'type': 'result', 'report': report, 'decision': decision})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            tb = traceback.format_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'traceback': tb})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def build_report(final_state, decision, ticker, trade_date):
    """Build structured report dict from final state."""
    sections = []

    # Analyst reports
    analysts = []
    if final_state.get("market_report"):
        analysts.append({"name": "Market Analyst", "content": final_state["market_report"]})
    if final_state.get("sentiment_report"):
        analysts.append({"name": "Social Analyst", "content": final_state["sentiment_report"]})
    if final_state.get("news_report"):
        analysts.append({"name": "News Analyst", "content": final_state["news_report"]})
    if final_state.get("fundamentals_report"):
        analysts.append({"name": "Fundamentals Analyst", "content": final_state["fundamentals_report"]})
    if analysts:
        sections.append({"title": "Analyst Reports", "items": analysts})

    # Research team
    debate = final_state.get("investment_debate_state", {})
    research = []
    if debate.get("bull_history"):
        research.append({"name": "Bull Researcher", "content": debate["bull_history"]})
    if debate.get("bear_history"):
        research.append({"name": "Bear Researcher", "content": debate["bear_history"]})
    if debate.get("judge_decision"):
        research.append({"name": "Research Manager", "content": debate["judge_decision"]})
    if research:
        sections.append({"title": "Research Team", "items": research})

    # Trading plan
    if final_state.get("trader_investment_plan"):
        sections.append({
            "title": "Trading Plan",
            "items": [{"name": "Trader", "content": final_state["trader_investment_plan"]}]
        })

    # Risk assessment
    risk = final_state.get("risk_debate_state", {})
    risk_items = []
    if risk.get("aggressive_history"):
        risk_items.append({"name": "Aggressive View", "content": risk["aggressive_history"]})
    if risk.get("conservative_history"):
        risk_items.append({"name": "Conservative View", "content": risk["conservative_history"]})
    if risk.get("neutral_history"):
        risk_items.append({"name": "Neutral View", "content": risk["neutral_history"]})
    if risk_items:
        sections.append({"title": "Risk Assessment", "items": risk_items})

    # Final decision
    if final_state.get("final_trade_decision"):
        sections.append({
            "title": "Final Trade Decision",
            "items": [{"name": "Portfolio Manager", "content": final_state["final_trade_decision"]}]
        })

    return {
        "ticker": ticker,
        "date": trade_date,
        "decision": decision,
        "sections": sections,
    }
