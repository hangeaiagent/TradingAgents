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
from datetime import date
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
AGENTPIT_CLIENT_ID = os.environ.get("AGENTPIT_CLIENT_ID", "cmnkfxkb1002860t9jy07egg5")
AGENTPIT_CLIENT_SECRET = os.environ.get("AGENTPIT_CLIENT_SECRET", "cmnkfxkb1002960t9d86xm8n4")
AGENTPIT_REDIRECT_URI = os.environ.get(
    "AGENTPIT_REDIRECT_URI", "https://trading.agentpit.io/api/auth/agentpit/callback"
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
# SQLite database
# ---------------------------------------------------------------------------
from web.database import Database
db = Database()


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
    language: Optional[str] = None


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

    config["output_language"] = req.language or "zh"
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


@app.get("/sso-callback", response_class=HTMLResponse)
async def sso_callback_page(request: Request):
    html_path = Path(__file__).parent / "static" / "sso-callback.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    if not request.session.get("access_token"):
        return RedirectResponse(url="/", status_code=302)
    html_path = Path(__file__).parent / "static" / "billing.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    if not request.session.get("access_token"):
        return RedirectResponse(url="/", status_code=302)
    html_path = Path(__file__).parent / "static" / "history.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request):
    if not request.session.get("access_token"):
        return RedirectResponse(url="/", status_code=302)
    html_path = Path(__file__).parent / "static" / "feedback.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------

@app.get("/api/auth/login")
async def auth_login(request: Request):
    """Legacy login redirect — forwards to /api/auth/agentpit/login."""
    return RedirectResponse(url="/api/auth/agentpit/login", status_code=302)


@app.get("/api/auth/agentpit/login")
async def auth_agentpit_login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = urlencode({
        "response_type": "code",
        "client_id": AGENTPIT_CLIENT_ID,
        "redirect_uri": AGENTPIT_REDIRECT_URI,
        "state": state,
    })
    return RedirectResponse(url=f"{AGENTPIT_AUTHORIZE_URL}?{params}")


@app.get("/api/auth/agentpit/sso")
async def auth_agentpit_sso(request: Request):
    """SSO entry — silent OAuth redirect with sso: prefixed state for anti-loop."""
    if request.session.get("access_token"):
        return RedirectResponse(url="/", status_code=302)
    state = "sso:" + secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = urlencode({
        "response_type": "code",
        "client_id": AGENTPIT_CLIENT_ID,
        "redirect_uri": AGENTPIT_REDIRECT_URI,
        "state": state,
    })
    return RedirectResponse(url=f"{AGENTPIT_AUTHORIZE_URL}?{params}")


async def _exchange_code_and_set_session(request: Request, code: str, access_token_out: list):
    """Exchange authorization code for token and populate session. Returns access_token."""
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

    access_token = token_data.get("access_token")
    if not access_token:
        return None
    access_token_out.append(access_token)
    request.session["access_token"] = access_token

    # Fetch user profile
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                AGENTPIT_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            log.info("[USERINFO] callback fetch: status=%s body=%s", resp.status_code, resp.text[:500])
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
                db.upsert_user(
                    request.session["user_id"],
                    request.session["user_name"],
                    request.session["user_email"],
                    request.session["user_avatar"],
                )
            else:
                log.warning("userinfo returned %s", resp.status_code)
    except Exception as e:
        log.warning("userinfo fetch failed: %s", e)
    request.session.setdefault("user_id", access_token[:16])
    return access_token


@app.get("/api/auth/agentpit/callback")
async def auth_agentpit_callback(request: Request, code: str = "", state: str = ""):
    saved_state = request.session.pop("oauth_state", None)
    is_sso = state.startswith("sso:") if state else False

    if not state or state != saved_state:
        if is_sso:
            # SSO failed — redirect to login page with error flag (no loop)
            return RedirectResponse(url="/?sso_error=state_mismatch", status_code=302)
        return HTMLResponse("<h3>state mismatch — please login again</h3>", status_code=400)
    if not code:
        if is_sso:
            return RedirectResponse(url="/?sso_error=no_code", status_code=302)
        return HTMLResponse("<h3>missing authorization code</h3>", status_code=400)

    try:
        token_out: list = []
        await _exchange_code_and_set_session(request, code, token_out)
        if not token_out:
            if is_sso:
                return RedirectResponse(url="/?sso_error=no_token", status_code=302)
            return HTMLResponse("<h3>No access_token received</h3>", status_code=502)
    except Exception as e:
        if is_sso:
            return RedirectResponse(url=f"/?sso_error=exchange_failed", status_code=302)
        return HTMLResponse(f"<h3>Token exchange failed: {e}</h3>", status_code=502)

    if is_sso:
        # SSO mode: redirect to SSO callback page which notifies frontend via hash token
        return RedirectResponse(url=f"/sso-callback#token={token_out[0]}", status_code=302)

    return RedirectResponse(url="/", status_code=302)


# Keep legacy callback path working (redirect to new path)
@app.get("/api/auth/callback")
async def auth_callback_legacy(request: Request, code: str = "", state: str = ""):
    """Legacy callback — redirect to new agentpit callback path."""
    params = urlencode({"code": code, "state": state})
    return RedirectResponse(url=f"/api/auth/agentpit/callback?{params}", status_code=302)


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
                        # Persist user to DB on lazy fetch too
                        db.upsert_user(
                            request.session["user_id"],
                            request.session["user_name"],
                            request.session["user_email"],
                            request.session["user_avatar"],
                        )
            except Exception as e:
                log.warning("userinfo lazy fetch failed: %s", e)

    user_id = request.session.get("user_id", "")
    usage = db.get_usage_summary(user_id)

    return {
        "user_id": user_id,
        "name": request.session.get("user_name", ""),
        "email": request.session.get("user_email", ""),
        "avatar": request.session.get("user_avatar", ""),
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# Routes — history
# ---------------------------------------------------------------------------

@app.get("/api/history")
async def get_history(request: Request, _auth=Depends(require_auth)):
    """Return analysis history (without report body in list)."""
    user_id = request.session.get("user_id", "")
    items = db.get_history(user_id)
    return {"items": items}


@app.get("/api/history/{record_id}")
async def get_history_detail(record_id: int, request: Request, _auth=Depends(require_auth)):
    """Return a single history record with full report."""
    user_id = request.session.get("user_id", "")
    record = db.get_record(record_id, user_id)
    if not record:
        return JSONResponse({"error": "not found"}, status_code=404)
    return record


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

        _record_usage(request, req.ticker, trade_date, decision, stats, elapsed_ms, model_name,
                      report=report)

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
                request, req.ticker, trade_date, decision, stats, elapsed_ms, model_name,
                report=report,
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

def _record_usage(request, ticker, trade_date, decision, stats, elapsed_ms, model_name,
                   report=None):
    user_id = request.session.get("user_id", "")
    return db.record_analysis(
        user_id=user_id,
        ticker=ticker,
        trade_date=trade_date,
        decision=decision,
        tokens_in=stats.get("tokens_in", 0),
        tokens_out=stats.get("tokens_out", 0),
        llm_calls=stats.get("llm_calls", 0),
        tool_calls=stats.get("tool_calls", 0),
        elapsed_ms=elapsed_ms,
        model=model_name,
        report=report,
    )


# ---------------------------------------------------------------------------
# Token consumption reporting (agentpit-tokens)
# ---------------------------------------------------------------------------

class TokenReportRequest(BaseModel):
    agent_id: str
    tokens_used: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    model_name: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Optional[dict] = None


@app.post("/api/v1/tokens/report")
async def report_tokens(req: TokenReportRequest, request: Request):
    """Token consumption reporting endpoint.

    Accepts Bearer token auth (ApiKey or access_token) and records
    token usage for the given agent.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"success": False, "error": "Missing or invalid Authorization header"}, status_code=401)

    bearer_token = auth_header[7:]
    if not bearer_token:
        return JSONResponse({"success": False, "error": "Empty bearer token"}, status_code=401)

    # Validate required fields
    if not req.agent_id:
        return JSONResponse({"success": False, "error": "agent_id is required"}, status_code=400)

    # Validate time order
    if req.started_at and req.ended_at and req.started_at >= req.ended_at:
        return JSONResponse({"success": False, "error": "started_at must be before ended_at"}, status_code=400)

    # Calculate tokens_used if not provided
    tokens_used = req.tokens_used
    if tokens_used is None:
        tokens_used = (req.input_tokens or 0) + (req.output_tokens or 0)

    # Record to database
    try:
        record_id = db.record_token_usage(
            agent_id=req.agent_id,
            bearer_token=bearer_token,
            tokens_used=tokens_used,
            input_tokens=req.input_tokens or 0,
            output_tokens=req.output_tokens or 0,
            started_at=req.started_at,
            ended_at=req.ended_at,
            model_name=req.model_name or "",
            request_id=req.request_id or "",
            metadata=req.metadata,
        )
    except Exception as e:
        log.error("Token report DB error: %s", e)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)

    return {
        "success": True,
        "data": {
            "id": record_id,
            "agent_id": req.agent_id,
            "tokens_used": tokens_used,
            "input_tokens": req.input_tokens or 0,
            "output_tokens": req.output_tokens or 0,
            "model_name": req.model_name or "",
        },
    }


# ---------------------------------------------------------------------------
# Routes — Evolvr webhook
# ---------------------------------------------------------------------------

EVOLVR_API = "https://evolvr.agentpit.io"
EVOLVR_APP_ID = "3846ced7-3eee-4df7-bcd1-049064d0af61"


@app.post("/api/evolvr/webhook")
async def evolvr_webhook(request: Request):
    """Receive Evolvr fix/deploy event callbacks."""
    data = await request.json()
    event = data.get("event", "")
    feedback_id = data.get("feedbackId", "")
    status = data.get("status", "")
    description = data.get("description", "")
    pr_url = data.get("prUrl", "")

    log.info(
        "[Evolvr Webhook] event=%s feedbackId=%s status=%s desc=%s",
        event, feedback_id, status, description[:80],
    )

    # Try to find the user who submitted this feedback via Evolvr API
    # and create an in-app notification for them
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Look up which user submitted this feedback
            resp = await client.get(
                f"{EVOLVR_API}/api/feedback/{feedback_id}/status"
            )
            if resp.status_code == 200:
                fb_data = resp.json()
                user_id = fb_data.get("userId") or fb_data.get("user_id")
                if user_id:
                    # Store notification in Evolvr (it already does this),
                    # just log for our records
                    log.info(
                        "[Evolvr Webhook] Notification for user=%s: %s → %s",
                        user_id, event, status,
                    )
    except Exception as e:
        log.warning("[Evolvr Webhook] Error processing callback: %s", e)

    return {"received": True}


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
