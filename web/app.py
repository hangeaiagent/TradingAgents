"""TradingAgents Web API — FastAPI backend for trading.agentpit.io"""

import os
import sys
import json
import asyncio
import secrets
import logging
import traceback
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
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

# --- AgentPit OAuth2 configuration ---
AGENTPIT_CLIENT_ID = os.environ.get("AGENTPIT_CLIENT_ID", "cmmvv7gpd000560c8yixfhvp4")
AGENTPIT_CLIENT_SECRET = os.environ.get("AGENTPIT_CLIENT_SECRET", "cmmvv7gpd000660c8mq0xfjk2")
AGENTPIT_REDIRECT_URI = os.environ.get("AGENTPIT_REDIRECT_URI", "https://trading.agentpit.io/api/auth/callback")
AGENTPIT_AUTHORIZE_URL = "https://agentpit.io/api/oauth/authorize"
AGENTPIT_TOKEN_URL = "https://agentpit.io/api/oauth/token"
AGENTPIT_USERINFO_URL = "https://agentpit.io/api/oauth/userinfo"
AGENTPIT_REPORT_USAGE_URL = os.environ.get(
    "AGENTPIT_REPORT_USAGE_URL", "https://agentpit.io/api/v1/partner/report-usage"
)
AGENTPIT_AGENT_ID = os.environ.get("AGENTPIT_AGENT_ID", "")

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", secrets.token_hex(32))

app = FastAPI(title="TradingAgents", docs_url="/api/docs")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="ta_session",
    max_age=86400,  # 24 hours
    same_site="lax",
    https_only=os.environ.get("HTTPS_ONLY", "true").lower() == "true",
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Serve skill files from project root
SKILLS_DIR = PROJECT_ROOT


# --- Auth helpers ---

async def require_auth(request: Request):
    """Dependency: reject unauthenticated requests."""
    if not request.session.get("access_token"):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized — please login via AgentPit")


log = logging.getLogger("tradingagents.web")


async def report_usage_to_agentpit(
    access_token: str,
    stats: dict,
    model_name: str,
    request_path: str,
    response_time_ms: int,
    response_status: int = 200,
):
    """Report token usage to AgentPit so it appears on the developer dashboard."""
    if not AGENTPIT_REPORT_USAGE_URL or not AGENTPIT_CLIENT_ID:
        return
    try:
        payload = {
            "client_id": AGENTPIT_CLIENT_ID,
            "client_secret": AGENTPIT_CLIENT_SECRET,
            "access_token": access_token,
            "agent_id": AGENTPIT_AGENT_ID or None,
            "input_tokens": stats.get("tokens_in", 0),
            "output_tokens": stats.get("tokens_out", 0),
            "model_name": model_name,
            "request_path": request_path,
            "response_time_ms": response_time_ms,
            "response_status": response_status,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(AGENTPIT_REPORT_USAGE_URL, json=payload)
            if resp.status_code != 200:
                log.warning("AgentPit usage report failed: %s %s", resp.status_code, resp.text)
            else:
                log.info("AgentPit usage reported: %s", resp.json())
    except Exception as e:
        log.warning("AgentPit usage report error: %s", e)


class AnalysisRequest(BaseModel):
    ticker: str
    trade_date: Optional[str] = None
    depth: str = "full"  # full or quick
    llm_provider: str = "google"
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
        # One-API provides an OpenAI-compatible endpoint that proxies to
        # upstream models (e.g. Gemini).  Route through the OpenAI client
        # so we don't need a native GOOGLE_API_KEY.
        config["llm_provider"] = "openai"

    return config


def get_analysts(depth: str):
    if depth == "quick":
        return ["news", "social"]
    return ["market", "social", "news", "fundamentals"]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if request.session.get("access_token"):
        html_path = Path(__file__).parent / "static" / "index.html"
    else:
        html_path = Path(__file__).parent / "static" / "login.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/auth/login")
async def auth_login(request: Request):
    """Redirect user to AgentPit OAuth2 authorization page."""
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = urlencode({
        "response_type": "code",
        "client_id": AGENTPIT_CLIENT_ID,
        "redirect_uri": AGENTPIT_REDIRECT_URI,
        "state": state,
    })
    return RedirectResponse(url=f"{AGENTPIT_AUTHORIZE_URL}?{params}")


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = ""):
    """Handle AgentPit OAuth2 callback: exchange code for token."""
    # Validate state to prevent CSRF
    saved_state = request.session.pop("oauth_state", None)
    if not state or state != saved_state:
        return HTMLResponse("<h3>授权失败：state 校验不通过，请重新登录</h3>", status_code=400)

    if not code:
        return HTMLResponse("<h3>授权失败：未收到授权码</h3>", status_code=400)

    # Exchange authorization code for access token
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(AGENTPIT_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": AGENTPIT_REDIRECT_URI,
                "client_id": AGENTPIT_CLIENT_ID,
                "client_secret": AGENTPIT_CLIENT_SECRET,
            })
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as e:
        return HTMLResponse(f"<h3>获取 Token 失败：{e}</h3>", status_code=502)

    access_token = token_data.get("access_token")
    if not access_token:
        return HTMLResponse("<h3>授权失败：未获取到 access_token</h3>", status_code=502)

    # Store token in session
    request.session["access_token"] = access_token
    return RedirectResponse(url="/", status_code=302)


@app.get("/api/auth/logout")
async def auth_logout(request: Request):
    """Clear session and redirect to login page."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


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
async def analyze_sync(req: AnalysisRequest, request: Request, _auth=Depends(require_auth)):
    """Synchronous analysis endpoint — returns full JSON result (for curl/OpenClaw)."""
    trade_date = req.trade_date or date.today().strftime("%Y-%m-%d")
    t0 = time.time()

    try:
        config = build_config(req)
        analysts = get_analysts(req.depth)

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from cli.stats_handler import StatsCallbackHandler

        stats_cb = StatsCallbackHandler()

        def run_analysis():
            ta = TradingAgentsGraph(
                selected_analysts=analysts, debug=False, config=config,
                callbacks=[stats_cb],
            )
            return ta.propagate(req.ticker, trade_date)

        loop = asyncio.get_event_loop()
        final_state, decision = await loop.run_in_executor(None, run_analysis)

        report = build_report(final_state, decision, req.ticker, trade_date)

        elapsed_ms = int((time.time() - t0) * 1000)
        access_token = request.session.get("access_token", "")
        model_name = req.model or config.get("deep_think_llm", "")
        asyncio.ensure_future(report_usage_to_agentpit(
            access_token, stats_cb.get_stats(), model_name,
            "/api/analyze/sync", elapsed_ms, 200,
        ))

        return {"status": "ok", "report": report, "decision": decision}

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@app.post("/api/analyze")
async def analyze(req: AnalysisRequest, request: Request, _auth=Depends(require_auth)):
    """Run analysis and stream results via SSE."""
    trade_date = req.trade_date or date.today().strftime("%Y-%m-%d")
    access_token = request.session.get("access_token", "")

    async def event_stream():
        yield f"data: {json.dumps({'type': 'status', 'message': f'Initializing analysis for {req.ticker}...'})}\n\n"
        t0 = time.time()

        try:
            config = build_config(req)
            analysts = get_analysts(req.depth)

            yield f"data: {json.dumps({'type': 'status', 'message': f'Running {req.depth} analysis ({len(analysts)} agents)...'})}\n\n"

            # Run in thread to not block event loop
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from cli.stats_handler import StatsCallbackHandler

            stats_cb = StatsCallbackHandler()

            def run_analysis():
                ta = TradingAgentsGraph(
                    selected_analysts=analysts, debug=False, config=config,
                    callbacks=[stats_cb],
                )
                return ta.propagate(req.ticker, trade_date)

            loop = asyncio.get_event_loop()
            final_state, decision = await loop.run_in_executor(None, run_analysis)

            # Build report sections
            report = build_report(final_state, decision, req.ticker, trade_date)

            yield f"data: {json.dumps({'type': 'result', 'report': report, 'decision': decision})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            elapsed_ms = int((time.time() - t0) * 1000)
            model_name = req.model or config.get("deep_think_llm", "")
            await report_usage_to_agentpit(
                access_token, stats_cb.get_stats(), model_name,
                "/api/analyze", elapsed_ms, 200,
            )

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
