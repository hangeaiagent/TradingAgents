"""PostgreSQL database module for TradingAgents web app.

All tables use the `trading_` prefix to coexist safely in the shared
`agentpit` database.  Uses psycopg2 connection pool for high concurrency.
Falls back to local SQLite when DATABASE_URL is not set (dev mode).
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("tradingagents.web.db")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_JSON = PROJECT_ROOT / "data" / "web_usage.json"
LEGACY_SQLITE = PROJECT_ROOT / "data" / "trading.db"

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ---------------------------------------------------------------------------
# PostgreSQL DDL
# ---------------------------------------------------------------------------
_PG_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS trading_users (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    avatar TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trading_analysis_records (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES trading_users(user_id),
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    decision TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,
    elapsed_ms INTEGER DEFAULT 0,
    model TEXT,
    report_json TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trading_records_user
    ON trading_analysis_records(user_id, timestamp);

CREATE TABLE IF NOT EXISTS trading_token_usage (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    bearer_token TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    model_name TEXT,
    request_id TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trading_token_usage_agent
    ON trading_token_usage(agent_id, created_at);
"""

# ---------------------------------------------------------------------------
# SQLite DDL (fallback)
# ---------------------------------------------------------------------------
_SQLITE_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS trading_users (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    avatar TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_analysis_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    decision TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,
    elapsed_ms INTEGER DEFAULT 0,
    model TEXT,
    report_json TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES trading_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_trading_records_user
    ON trading_analysis_records(user_id, timestamp);

CREATE TABLE IF NOT EXISTS trading_token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    bearer_token TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    model_name TEXT,
    request_id TEXT,
    metadata_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trading_token_usage_agent
    ON trading_token_usage(agent_id, created_at);
"""


class Database:
    """Unified DB wrapper. Uses PostgreSQL when DATABASE_URL is set,
    otherwise falls back to local SQLite for development."""

    def __init__(self):
        if DATABASE_URL:
            self._backend = "pg"
            self._init_pg()
        else:
            self._backend = "sqlite"
            self._init_sqlite()
        self._init_tables()
        self._migrate_legacy_sources()

    # ==================================================================
    # Backend initialisation
    # ==================================================================

    def _init_pg(self):
        from psycopg2 import pool
        # min 2, max 10 connections
        self._pool = pool.ThreadedConnectionPool(2, 10, DATABASE_URL)
        log.info("PostgreSQL pool created → %s", DATABASE_URL.split("@")[-1])

    def _init_sqlite(self):
        import sqlite3
        db_path = PROJECT_ROOT / "data" / "trading.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_path = str(db_path)
        self._local = threading.local()
        log.info("SQLite fallback → %s", db_path)

    # ==================================================================
    # Connection helpers
    # ==================================================================

    @contextmanager
    def _conn(self):
        """Yield a (connection, cursor) pair and handle commit/rollback."""
        if self._backend == "pg":
            conn = self._pool.getconn()
            try:
                cur = conn.cursor()
                yield conn, cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
                self._pool.putconn(conn)
        else:
            import sqlite3
            conn = getattr(self._local, "conn", None)
            if conn is None:
                conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                self._local.conn = conn
            cur = conn.cursor()
            yield conn, cur
            conn.commit()

    def _fetchone_dict(self, cur) -> dict | None:
        row = cur.fetchone()
        if row is None:
            return None
        if self._backend == "pg":
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        return dict(row)

    def _fetchall_dicts(self, cur) -> list[dict]:
        rows = cur.fetchall()
        if self._backend == "pg":
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
        return [dict(r) for r in rows]

    # Placeholder style: %s for PG, ? for SQLite
    @property
    def _ph(self):
        return "%s" if self._backend == "pg" else "?"

    def _sql(self, template: str) -> str:
        """Replace ? placeholders with %s for PostgreSQL."""
        if self._backend == "pg":
            return template.replace("?", "%s")
        return template

    # ==================================================================
    # Table creation
    # ==================================================================

    def _init_tables(self):
        with self._conn() as (conn, cur):
            if self._backend == "pg":
                cur.execute(_PG_CREATE_TABLES)
            else:
                conn.executescript(_SQLITE_CREATE_TABLES)
                conn.commit()

    # ==================================================================
    # Legacy migration (JSON → DB, SQLite → PG)
    # ==================================================================

    def _migrate_legacy_sources(self):
        # 1. Migrate from JSON file (if exists)
        self._migrate_legacy_json()
        # 2. If backend is PG, also migrate from local SQLite (if exists)
        if self._backend == "pg":
            self._migrate_legacy_sqlite()

    def _migrate_legacy_json(self):
        if not LEGACY_JSON.exists():
            return
        try:
            with open(LEGACY_JSON, encoding="utf-8") as f:
                data = json.load(f)
            count = 0
            with self._conn() as (conn, cur):
                for user_id, records in data.items():
                    if not isinstance(records, list):
                        continue
                    cur.execute(
                        self._sql("INSERT INTO trading_users (user_id) VALUES (?) ON CONFLICT (user_id) DO NOTHING"),
                        (user_id,),
                    )
                    for r in records:
                        cur.execute(
                            self._sql(
                                """INSERT INTO trading_analysis_records
                                   (user_id, ticker, trade_date, decision,
                                    tokens_in, tokens_out, llm_calls, tool_calls,
                                    elapsed_ms, model, report_json, timestamp)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"""
                            ),
                            (
                                user_id,
                                r.get("ticker", ""),
                                r.get("trade_date", ""),
                                r.get("decision", ""),
                                r.get("tokens_in", 0),
                                r.get("tokens_out", 0),
                                r.get("llm_calls", 0),
                                r.get("tool_calls", 0),
                                r.get("elapsed_ms", 0),
                                r.get("model", ""),
                                json.dumps(r.get("report"), ensure_ascii=False) if r.get("report") else None,
                                r.get("timestamp", datetime.now().isoformat()),
                            ),
                        )
                        count += 1
            backup = LEGACY_JSON.with_suffix(".json.bak")
            LEGACY_JSON.rename(backup)
            log.info("Migrated %d records from JSON → DB; backup at %s", count, backup)
        except Exception as e:
            log.warning("Legacy JSON migration failed: %s", e)

    def _migrate_legacy_sqlite(self):
        """Migrate data from local SQLite to PostgreSQL (one-time)."""
        if not LEGACY_SQLITE.exists():
            return
        try:
            import sqlite3
            src = sqlite3.connect(str(LEGACY_SQLITE))
            src.row_factory = sqlite3.Row

            # Check if data already migrated by looking at record count
            with self._conn() as (conn, cur):
                cur.execute("SELECT COUNT(*) FROM trading_analysis_records")
                pg_count = cur.fetchone()[0]
            if pg_count > 0:
                log.info("PostgreSQL already has %d records, skipping SQLite migration", pg_count)
                return

            users = src.execute("SELECT * FROM trading_users").fetchall()
            records = src.execute("SELECT * FROM trading_analysis_records").fetchall()
            count = 0

            with self._conn() as (conn, cur):
                for u in users:
                    u = dict(u)
                    cur.execute(
                        "INSERT INTO trading_users (user_id, name, email, avatar) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING",
                        (u["user_id"], u.get("name", ""), u.get("email", ""), u.get("avatar", "")),
                    )
                for r in records:
                    r = dict(r)
                    cur.execute(
                        """INSERT INTO trading_analysis_records
                           (user_id, ticker, trade_date, decision,
                            tokens_in, tokens_out, llm_calls, tool_calls,
                            elapsed_ms, model, report_json, timestamp)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            r["user_id"], r["ticker"], r["trade_date"], r.get("decision", ""),
                            r.get("tokens_in", 0), r.get("tokens_out", 0),
                            r.get("llm_calls", 0), r.get("tool_calls", 0),
                            r.get("elapsed_ms", 0), r.get("model", ""),
                            r.get("report_json"), r["timestamp"],
                        ),
                    )
                    count += 1
            src.close()
            backup = LEGACY_SQLITE.with_suffix(".db.bak")
            LEGACY_SQLITE.rename(backup)
            log.info("Migrated %d records from SQLite → PostgreSQL; backup at %s", count, backup)
        except Exception as e:
            log.warning("SQLite → PostgreSQL migration failed: %s", e)

    # ==================================================================
    # Users
    # ==================================================================

    def upsert_user(self, user_id: str, name: str = "", email: str = "", avatar: str = ""):
        with self._conn() as (conn, cur):
            if self._backend == "pg":
                cur.execute(
                    """INSERT INTO trading_users (user_id, name, email, avatar)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (user_id) DO UPDATE SET
                         name = COALESCE(NULLIF(EXCLUDED.name, ''), trading_users.name),
                         email = COALESCE(NULLIF(EXCLUDED.email, ''), trading_users.email),
                         avatar = COALESCE(NULLIF(EXCLUDED.avatar, ''), trading_users.avatar)""",
                    (user_id, name, email, avatar),
                )
            else:
                cur.execute(
                    """INSERT INTO trading_users (user_id, name, email, avatar)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         name = COALESCE(NULLIF(excluded.name, ''), trading_users.name),
                         email = COALESCE(NULLIF(excluded.email, ''), trading_users.email),
                         avatar = COALESCE(NULLIF(excluded.avatar, ''), trading_users.avatar)""",
                    (user_id, name, email, avatar),
                )

    # ==================================================================
    # Analysis records
    # ==================================================================

    def record_analysis(
        self,
        user_id: str,
        ticker: str,
        trade_date: str,
        decision: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        llm_calls: int = 0,
        tool_calls: int = 0,
        elapsed_ms: int = 0,
        model: str = "",
        report: dict | None = None,
    ) -> dict:
        ts = datetime.now().isoformat()
        report_json = json.dumps(report, ensure_ascii=False) if report else None
        with self._conn() as (conn, cur):
            if self._backend == "pg":
                cur.execute(
                    """INSERT INTO trading_analysis_records
                       (user_id, ticker, trade_date, decision,
                        tokens_in, tokens_out, llm_calls, tool_calls,
                        elapsed_ms, model, report_json, timestamp)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (user_id, ticker, trade_date, decision,
                     tokens_in, tokens_out, llm_calls, tool_calls,
                     elapsed_ms, model, report_json, ts),
                )
                record_id = cur.fetchone()[0]
            else:
                cur.execute(
                    """INSERT INTO trading_analysis_records
                       (user_id, ticker, trade_date, decision,
                        tokens_in, tokens_out, llm_calls, tool_calls,
                        elapsed_ms, model, report_json, timestamp)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (user_id, ticker, trade_date, decision,
                     tokens_in, tokens_out, llm_calls, tool_calls,
                     elapsed_ms, model, report_json, ts),
                )
                record_id = cur.lastrowid
        return {
            "id": record_id,
            "ticker": ticker,
            "trade_date": trade_date,
            "decision": decision,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "elapsed_ms": elapsed_ms,
            "model": model,
            "timestamp": ts,
        }

    def get_history(self, user_id: str) -> list[dict]:
        with self._conn() as (conn, cur):
            cur.execute(
                self._sql(
                    """SELECT id, ticker, trade_date, decision,
                              tokens_in, tokens_out, llm_calls, elapsed_ms,
                              model, timestamp,
                              CASE WHEN report_json IS NOT NULL THEN 1 ELSE 0 END AS has_report
                       FROM trading_analysis_records
                       WHERE user_id = ?
                       ORDER BY timestamp DESC"""
                ),
                (user_id,),
            )
            return self._fetchall_dicts(cur)

    def get_record(self, record_id: int, user_id: str) -> dict | None:
        with self._conn() as (conn, cur):
            cur.execute(
                self._sql(
                    """SELECT * FROM trading_analysis_records
                       WHERE id = ? AND user_id = ?"""
                ),
                (record_id, user_id),
            )
            d = self._fetchone_dict(cur)
        if not d:
            return None
        if d.get("report_json"):
            d["report"] = json.loads(d["report_json"])
        d.pop("report_json", None)
        return d

    def get_usage_summary(self, user_id: str) -> dict:
        with self._conn() as (conn, cur):
            # Totals
            cur.execute(
                self._sql(
                    """SELECT COUNT(*) AS total_analyses,
                              COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
                              COALESCE(SUM(tokens_out), 0) AS total_tokens_out,
                              COALESCE(SUM(llm_calls), 0) AS total_llm_calls,
                              COALESCE(SUM(elapsed_ms), 0) AS total_time_ms
                       FROM trading_analysis_records
                       WHERE user_id = ?"""
                ),
                (user_id,),
            )
            totals = self._fetchone_dict(cur)

            # Monthly aggregation
            cur.execute(
                self._sql(
                    """SELECT SUBSTR(timestamp, 1, 7) AS month,
                              COUNT(*) AS analyses,
                              SUM(tokens_in) AS tokens_in,
                              SUM(tokens_out) AS tokens_out,
                              SUM(llm_calls) AS llm_calls,
                              SUM(tool_calls) AS tool_calls,
                              SUM(elapsed_ms) AS total_time_ms
                       FROM trading_analysis_records
                       WHERE user_id = ?
                       GROUP BY SUBSTR(timestamp, 1, 7)
                       ORDER BY month DESC"""
                ),
                (user_id,),
            )
            monthly = self._fetchall_dicts(cur)

            # Recent records (last 50)
            cur.execute(
                self._sql(
                    """SELECT ticker, trade_date, decision,
                              tokens_in, tokens_out, llm_calls, tool_calls,
                              elapsed_ms, model, timestamp
                       FROM trading_analysis_records
                       WHERE user_id = ?
                       ORDER BY timestamp DESC
                       LIMIT 50"""
                ),
                (user_id,),
            )
            recent = self._fetchall_dicts(cur)

        return {
            "total_analyses": totals["total_analyses"],
            "total_tokens_in": totals["total_tokens_in"],
            "total_tokens_out": totals["total_tokens_out"],
            "total_llm_calls": totals["total_llm_calls"],
            "total_time_ms": totals["total_time_ms"],
            "monthly": monthly,
            "records": recent,
        }

    # ==================================================================
    # Token usage reporting (agentpit-tokens)
    # ==================================================================

    def record_token_usage(
        self,
        agent_id: str,
        bearer_token: str,
        tokens_used: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        started_at: str | None = None,
        ended_at: str | None = None,
        model_name: str = "",
        request_id: str = "",
        metadata: dict | None = None,
    ) -> int:
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        with self._conn() as (conn, cur):
            if self._backend == "pg":
                cur.execute(
                    """INSERT INTO trading_token_usage
                       (agent_id, bearer_token, tokens_used, input_tokens, output_tokens,
                        started_at, ended_at, model_name, request_id, metadata_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (agent_id, bearer_token, tokens_used, input_tokens, output_tokens,
                     started_at, ended_at, model_name, request_id, metadata_json),
                )
                return cur.fetchone()[0]
            else:
                cur.execute(
                    """INSERT INTO trading_token_usage
                       (agent_id, bearer_token, tokens_used, input_tokens, output_tokens,
                        started_at, ended_at, model_name, request_id, metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (agent_id, bearer_token, tokens_used, input_tokens, output_tokens,
                     started_at, ended_at, model_name, request_id, metadata_json),
                )
                return cur.lastrowid
