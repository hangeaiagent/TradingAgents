"""TradingAgents Web API — FastAPI backend for trading.agentpit.io"""

import os
import sys
import json
import asyncio
import secrets
import logging
import traceback
import time
import queue
import threading
import concurrent.futures
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Depends
from fastapi.responses import (
    HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse, PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ONE_API_KEY → OPENAI_API_KEY fallback
if os.environ.get("ONE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["ONE_API_KEY"]

# ---------------------------------------------------------------------------
# AgentPit OAuth2 configuration
# ---------------------------------------------------------------------------
AGENTPIT_CLIENT_ID = os.environ.get("AGENTPIT_CLIENT_ID", "cmmvv7gpd000560c8yixfhvp4")
AGENTPIT_CLIENT_SECRET = os.environ.get("AGENTPIT_CLIENT_SECRET", "cmmvv7gpd000660c8mq0xfjk2")
AGENTPIT_REDIRECT_URI = os.environ.get(
    "AGENTPIT_REDIRECT_URI", "https://trading.agentpit.io/api/auth/callback"
)
AGENTPIT_AUTHORIZE_URL = "https://agentpit.io/api/oauth/authorize"
AGENTPIT_TOKEN_URL = "https://agentpit.io/api/oauth/token"
AGENTPIT_USERINFO_URL = "https://agentpit.io/api/oauth/userinfo"
AGENTPIT_REPORT_USAGE_URL = os.environ.get(
    "AGENTPIT_REPORT_USAGE_URL", "https://agentpit.io/api/v1/partner/report-usage"
)
AGENTPIT_AGENT_ID = os.environ.get("AGENTPIT_AGENT_ID", "")

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", secrets.token_hex(32))

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="TradingAgents", docs_url="/api/docs")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="ta_session",
    max_age=86400,
    same_site="lax",
    https_only=os.environ.get("HTTPS_ONLY", "true").lower() == "true",
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

SKILLS_DIR = PROJECT_ROOT
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
log = logging.getLogger("tradingagents.web")

# ---------------------------------------------------------------------------
# In-memory usage store (persisted to disk)
# ---------------------------------------------------------------------------
USAGE_FILE = PROJECT_ROOT / "data" / "web_usage.json"
_usage_lock = threading.Lock()


def _load_usage_store() -> dict:
    if USAGE_FILE.exists():
        try:
            with open(USAGE_FILE, encoding="utf-8") as f:
                return defaultdict(list, json.load(f))
        except Exception:
            pass
    return defaultdict(list)


_usage_store: dict = _load_usage_store()


def _save_usage_store():
    with _usage_lock:
        try:
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(dict(_usage_store), f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning("Failed to save usage store: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def require_auth(request: Request):
    if not request.session.get("access_token"):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")


async def report_usage_to_agentpit(
    access_token, stats, model_name, request_path, response_time_ms, response_status=200,
):
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


# ---------------------------------------------------------------------------
# Models & config
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    ticker: str
    trade_date: Optional[str] = None
    depth: str = "full"
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


ANALYST_DISPLAY = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}


def get_pipeline_stages(analysts):
    """Build pipeline stages for the frontend timeline."""
    return [
        {"id": "analysts", "agents": [ANALYST_DISPLAY.get(a, a) for a in analysts]},
        {"id": "research", "agents": ["Bull Researcher", "Bear Researcher", "Research Manager"]},
        {"id": "trading", "agents": ["Trader"]},
        {"id": "risk", "agents": ["Aggressive Debater", "Conservative Debater", "Neutral Debater"]},
        {"id": "decision", "agents": ["Portfolio Manager"]},
    ]


# Fields to watch for progress detection during graph streaming.
# (top-level field, nested field or None, display agent name, stage id)
_PROGRESS_FIELDS = [
    ("market_report", None, "Market Analyst", "analysts"),
    ("sentiment_report", None, "Social Analyst", "analysts"),
    ("news_report", None, "News Analyst", "analysts"),
    ("fundamentals_report", None, "Fundamentals Analyst", "analysts"),
    ("investment_debate_state", "bull_history", "Bull Researcher", "research"),
    ("investment_debate_state", "bear_history", "Bear Researcher", "research"),
    ("investment_debate_state", "judge_decision", "Research Manager", "research"),
    ("trader_investment_plan", None, "Trader", "trading"),
    ("risk_debate_state", "aggressive_history", "Aggressive Debater", "risk"),
    ("risk_debate_state", "conservative_history", "Conservative Debater", "risk"),
    ("risk_debate_state", "neutral_history", "Neutral Debater", "risk"),
    ("final_trade_decision", None, "Portfolio Manager", "decision"),
]


# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if request.session.get("access_token"):
        html_path = Path(__file__).parent / "static" / "index.html"
    else:
        html_path = Path(__file__).parent / "static" / "login.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    if not request.session.get("access_token"):
        return RedirectResponse(url="/", status_code=302)
    html_path = Path(__file__).parent / "static" / "billing.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------

@app.get("/api/auth/login")
async def auth_login(request: Request):
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
    saved_state = request.session.pop("oauth_state", None)
    if not state or state != saved_state:
        return HTMLResponse("<h3>state mismatch — please login again</h3>", status_code=400)
    if not code:
        return HTMLResponse("<h3>missing authorization code</h3>", status_code=400)

    # Exchange code → token
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
        return HTMLResponse(f"<h3>Token exchange failed: {e}</h3>", status_code=502)

    access_token = token_data.get("access_token")
    if not access_token:
        return HTMLResponse("<h3>No access_token received</h3>", status_code=502)

    request.session["access_token"] = access_token

    # Fetch user profile
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                AGENTPIT_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            print(f"[USERINFO] callback fetch: status={resp.status_code} body={resp.text[:500]}", flush=True)
            if resp.status_code == 200:
                info = resp.json()
                # Try common field names
                request.session["user_name"] = (
                    info.get("name") or info.get("username") or info.get("login")
                    or info.get("displayName") or info.get("nickname") or ""
                )
                request.session["user_email"] = (
                    info.get("email") or info.get("mail") or ""
                )
                request.session["user_avatar"] = (
                    info.get("avatar") or info.get("picture")
                    or info.get("avatarUrl") or info.get("avatar_url") or ""
                )
                request.session["user_id"] = str(
                    info.get("id") or info.get("sub")
                    or info.get("userId") or info.get("user_id")
                    or access_token[:16]
                )
            else:
                log.warning("userinfo returned %s", resp.status_code)
    except Exception as e:
        log.warning("userinfo fetch failed: %s", e)
    request.session.setdefault("user_id", access_token[:16])

    return RedirectResponse(url="/", status_code=302)


@app.get("/api/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


# ---------------------------------------------------------------------------
# Routes — user info & usage
# ---------------------------------------------------------------------------

@app.get("/api/user/info")
async def user_info(request: Request, _auth=Depends(require_auth)):
    # If session lacks user profile, try fetching it now (handles old sessions)
    if not request.session.get("user_name") and not request.session.get("user_email"):
        access_token = request.session.get("access_token", "")
        if access_token:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        AGENTPIT_USERINFO_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    print(f"[USERINFO] lazy fetch: status={resp.status_code} body={resp.text[:500]}", flush=True)
                    if resp.status_code == 200:
                        info = resp.json()
                        request.session["user_name"] = (
                            info.get("name") or info.get("username") or info.get("login")
                            or info.get("displayName") or info.get("nickname") or ""
                        )
                        request.session["user_email"] = (
                            info.get("email") or info.get("mail") or ""
                        )
                        request.session["user_avatar"] = (
                            info.get("avatar") or info.get("picture")
                            or info.get("avatarUrl") or info.get("avatar_url") or ""
                        )
                        request.session["user_id"] = str(
                            info.get("id") or info.get("sub")
                            or info.get("userId") or info.get("user_id")
                            or access_token[:16]
                        )
            except Exception as e:
                log.warning("userinfo lazy fetch failed: %s", e)

    user_id = request.session.get("user_id", "")
    records = _usage_store.get(user_id, [])

    # Monthly aggregation
    monthly: dict = {}
    for r in records:
        ts = r.get("timestamp", "")
        month_key = ts[:7] if len(ts) >= 7 else "unknown"  # "2026-03"
        if month_key not in monthly:
            monthly[month_key] = {
                "month": month_key, "analyses": 0,
                "tokens_in": 0, "tokens_out": 0,
                "llm_calls": 0, "tool_calls": 0, "total_time_ms": 0,
            }
        m = monthly[month_key]
        m["analyses"] += 1
        m["tokens_in"] += r.get("tokens_in", 0)
        m["tokens_out"] += r.get("tokens_out", 0)
        m["llm_calls"] += r.get("llm_calls", 0)
        m["tool_calls"] += r.get("tool_calls", 0)
        m["total_time_ms"] += r.get("elapsed_ms", 0)

    # Sort months descending
    monthly_list = sorted(monthly.values(), key=lambda x: x["month"], reverse=True)

    return {
        "name": request.session.get("user_name", ""),
        "email": request.session.get("user_email", ""),
        "avatar": request.session.get("user_avatar", ""),
        "usage": {
            "total_analyses": len(records),
            "total_tokens_in": sum(r.get("tokens_in", 0) for r in records),
            "total_tokens_out": sum(r.get("tokens_out", 0) for r in records),
            "total_llm_calls": sum(r.get("llm_calls", 0) for r in records),
            "total_time_ms": sum(r.get("elapsed_ms", 0) for r in records),
            "monthly": monthly_list,
            "records": records[-50:],  # last 50
        },
    }


# ---------------------------------------------------------------------------
# Routes — skills
# ---------------------------------------------------------------------------

@app.get("/skills/{skill_name}.md")
async def get_skill(skill_name: str):
    safe_name = skill_name.replace("..", "").replace("/", "")
    skill_path = SKILLS_DIR / "skills_openclaw" / f"{safe_name}.md"
    if not skill_path.exists():
        return JSONResponse({"error": "skill not found"}, status_code=404)
    return PlainTextResponse(skill_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Routes — analysis (sync)
# ---------------------------------------------------------------------------

@app.post("/api/analyze/sync")
async def analyze_sync(req: AnalysisRequest, request: Request, _auth=Depends(require_auth)):
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
        stats = stats_cb.get_stats()

        _record_usage(request, req.ticker, trade_date, decision, stats, elapsed_ms, model_name)

        asyncio.ensure_future(report_usage_to_agentpit(
            access_token, stats, model_name, "/api/analyze/sync", elapsed_ms, 200,
        ))
        return {"status": "ok", "report": report, "decision": decision}

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# Routes — analysis (SSE streaming with progress)
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def analyze(req: AnalysisRequest, request: Request, _auth=Depends(require_auth)):
    trade_date = req.trade_date or date.today().strftime("%Y-%m-%d")
    access_token = request.session.get("access_token", "")

    async def event_stream():
        t0 = time.time()

        try:
            config = build_config(req)
            analysts = get_analysts(req.depth)

            # Send pipeline so frontend can render timeline immediately
            yield sse({"type": "pipeline", "stages": get_pipeline_stages(analysts)})
            yield sse({
                "type": "status",
                "message": f"Initializing analysis for {req.ticker}...",
            })

            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from cli.stats_handler import StatsCallbackHandler

            stats_cb = StatsCallbackHandler()
            progress_q: queue.Queue = queue.Queue()

            def run_analysis():
                ta = TradingAgentsGraph(
                    selected_analysts=analysts, debug=False, config=config,
                    callbacks=[stats_cb],
                )
                ta.ticker = req.ticker

                init_state = ta.propagator.create_initial_state(req.ticker, trade_date)
                args = ta.propagator.get_graph_args()

                seen: set = set()
                final_state = None

                for state in ta.graph.stream(init_state, **args):
                    final_state = state
                    _detect_progress(state, seen, progress_q)

                if final_state is None:
                    raise RuntimeError("Analysis produced no output")

                ta.curr_state = final_state
                ta._log_state(trade_date, final_state)
                decision = ta.process_signal(
                    final_state.get("final_trade_decision", "")
                )
                return final_state, decision

            # Run in background thread, poll progress queue
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(run_analysis)

            while not future.done():
                await asyncio.sleep(0.4)
                while not progress_q.empty():
                    try:
                        yield sse(progress_q.get_nowait())
                    except queue.Empty:
                        break

            # Drain remaining progress events
            while not progress_q.empty():
                try:
                    yield sse(progress_q.get_nowait())
                except queue.Empty:
                    break

            final_state, decision = future.result()
            executor.shutdown(wait=False)

            report = build_report(final_state, decision, req.ticker, trade_date)
            elapsed_ms = int((time.time() - t0) * 1000)
            model_name = req.model or config.get("deep_think_llm", "")
            stats = stats_cb.get_stats()

            usage_record = _record_usage(
                request, req.ticker, trade_date, decision, stats, elapsed_ms, model_name
            )

            yield sse({
                "type": "result",
                "report": report,
                "decision": decision,
                "usage": usage_record,
            })
            yield sse({"type": "done"})

            await report_usage_to_agentpit(
                access_token, stats, model_name, "/api/analyze", elapsed_ms, 200,
            )

        except Exception as e:
            tb = traceback.format_exc()
            yield sse({"type": "error", "message": str(e), "traceback": tb})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Progress detection
# ---------------------------------------------------------------------------

def _detect_progress(state: dict, seen: set, q: queue.Queue):
    """Compare current state against seen set and emit progress events."""
    for top_field, nested_field, agent, stage in _PROGRESS_FIELDS:
        if agent in seen:
            continue
        if nested_field:
            parent = state.get(top_field)
            val = parent.get(nested_field, "") if isinstance(parent, dict) else ""
        else:
            val = state.get(top_field, "")
        if val:
            seen.add(agent)
            preview = val[:300] + "..." if len(str(val)) > 300 else str(val)
            q.put({"type": "progress", "agent": agent, "stage": stage, "preview": preview})


# ---------------------------------------------------------------------------
# Usage recording
# ---------------------------------------------------------------------------

def _record_usage(request, ticker, trade_date, decision, stats, elapsed_ms, model_name):
    user_id = request.session.get("user_id", "")
    record = {
        "ticker": ticker,
        "trade_date": trade_date,
        "decision": decision,
        "tokens_in": stats.get("tokens_in", 0),
        "tokens_out": stats.get("tokens_out", 0),
        "llm_calls": stats.get("llm_calls", 0),
        "tool_calls": stats.get("tool_calls", 0),
        "elapsed_ms": elapsed_ms,
        "model": model_name,
        "timestamp": datetime.now().isoformat(),
    }
    _usage_store[user_id].append(record)
    _save_usage_store()
    return record


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(final_state, decision, ticker, trade_date):
    sections = []

    analyst_items = []
    for key, name in [
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Social Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
    ]:
        if final_state.get(key):
            analyst_items.append({"name": name, "content": final_state[key]})
    if analyst_items:
        sections.append({"title": "Analyst Reports", "items": analyst_items})

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

    if final_state.get("trader_investment_plan"):
        sections.append({
            "title": "Trading Plan",
            "items": [{"name": "Trader", "content": final_state["trader_investment_plan"]}],
        })

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

    if final_state.get("final_trade_decision"):
        sections.append({
            "title": "Final Trade Decision",
            "items": [{"name": "Portfolio Manager", "content": final_state["final_trade_decision"]}],
        })

    return {"ticker": ticker, "date": trade_date, "decision": decision, "sections": sections}
