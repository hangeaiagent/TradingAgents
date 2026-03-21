"""SQLite database module for TradingAgents web app.

Replaces the JSON-based usage store with a proper SQLite database.
All tables use the `trading_` prefix to avoid conflicts with other apps
sharing the same data directory.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("tradingagents.web.db")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trading.db"
LEGACY_JSON = PROJECT_ROOT / "data" / "web_usage.json"

_CREATE_TABLES = """
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
"""


class Database:
    """Thread-safe SQLite wrapper using WAL mode and per-thread connections."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._local = threading.local()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        self._migrate_legacy_json()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _init_tables(self):
        conn = self._get_conn()
        conn.executescript(_CREATE_TABLES)
        conn.commit()

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def _migrate_legacy_json(self):
        if not LEGACY_JSON.exists():
            return
        try:
            with open(LEGACY_JSON, encoding="utf-8") as f:
                data = json.load(f)
            conn = self._get_conn()
            count = 0
            for user_id, records in data.items():
                if not isinstance(records, list):
                    continue
                for r in records:
                    conn.execute(
                        """INSERT INTO trading_analysis_records
                           (user_id, ticker, trade_date, decision,
                            tokens_in, tokens_out, llm_calls, tool_calls,
                            elapsed_ms, model, report_json, timestamp)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            conn.commit()
            # Rename old file so we don't re-migrate
            backup = LEGACY_JSON.with_suffix(".json.bak")
            LEGACY_JSON.rename(backup)
            log.info("Migrated %d records from %s → SQLite; backup at %s", count, LEGACY_JSON, backup)
        except Exception as e:
            log.warning("Legacy JSON migration failed: %s", e)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def upsert_user(self, user_id: str, name: str = "", email: str = "", avatar: str = ""):
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO trading_users (user_id, name, email, avatar)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 name = COALESCE(NULLIF(excluded.name, ''), trading_users.name),
                 email = COALESCE(NULLIF(excluded.email, ''), trading_users.email),
                 avatar = COALESCE(NULLIF(excluded.avatar, ''), trading_users.avatar)""",
            (user_id, name, email, avatar),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Analysis records
    # ------------------------------------------------------------------

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
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO trading_analysis_records
               (user_id, ticker, trade_date, decision,
                tokens_in, tokens_out, llm_calls, tool_calls,
                elapsed_ms, model, report_json, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, ticker, trade_date, decision,
             tokens_in, tokens_out, llm_calls, tool_calls,
             elapsed_ms, model, report_json, ts),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
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
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, ticker, trade_date, decision,
                      tokens_in, tokens_out, llm_calls, elapsed_ms,
                      model, timestamp, report_json IS NOT NULL AS has_report
               FROM trading_analysis_records
               WHERE user_id = ?
               ORDER BY timestamp DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_record(self, record_id: int, user_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            """SELECT * FROM trading_analysis_records
               WHERE id = ? AND user_id = ?""",
            (record_id, user_id),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("report_json"):
            d["report"] = json.loads(d["report_json"])
        d.pop("report_json", None)
        return d

    def get_usage_summary(self, user_id: str) -> dict:
        conn = self._get_conn()

        # Totals
        totals = conn.execute(
            """SELECT COUNT(*) AS total_analyses,
                      COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
                      COALESCE(SUM(tokens_out), 0) AS total_tokens_out,
                      COALESCE(SUM(llm_calls), 0) AS total_llm_calls,
                      COALESCE(SUM(elapsed_ms), 0) AS total_time_ms
               FROM trading_analysis_records
               WHERE user_id = ?""",
            (user_id,),
        ).fetchone()

        # Monthly aggregation
        monthly_rows = conn.execute(
            """SELECT SUBSTR(timestamp, 1, 7) AS month,
                      COUNT(*) AS analyses,
                      SUM(tokens_in) AS tokens_in,
                      SUM(tokens_out) AS tokens_out,
                      SUM(llm_calls) AS llm_calls,
                      SUM(tool_calls) AS tool_calls,
                      SUM(elapsed_ms) AS total_time_ms
               FROM trading_analysis_records
               WHERE user_id = ?
               GROUP BY month
               ORDER BY month DESC""",
            (user_id,),
        ).fetchall()

        # Recent records (last 50)
        recent = conn.execute(
            """SELECT ticker, trade_date, decision,
                      tokens_in, tokens_out, llm_calls, tool_calls,
                      elapsed_ms, model, timestamp
               FROM trading_analysis_records
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT 50""",
            (user_id,),
        ).fetchall()

        return {
            "total_analyses": totals["total_analyses"],
            "total_tokens_in": totals["total_tokens_in"],
            "total_tokens_out": totals["total_tokens_out"],
            "total_llm_calls": totals["total_llm_calls"],
            "total_time_ms": totals["total_time_ms"],
            "monthly": [dict(r) for r in monthly_rows],
            "records": [dict(r) for r in recent],
        }
