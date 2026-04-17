"""SQLite persistence layer — from .openjarvis pattern."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class TelemetryEvent:
    """A telemetry event for analytics."""
    event_type: str
    timestamp: float
    data: dict
    session_id: str = ""


@dataclass
class ExecutionTrace:
    """An execution trace for debugging."""
    trace_id: str
    tool_name: str
    input_data: dict
    output_data: dict
    success: bool
    elapsed_ms: float
    timestamp: float
    error: Optional[str] = None


class DatabaseManager:
    """Manages SQLite databases for FRIDAY.

    Pattern from .openjarvis:
    - agents.db: Agent configurations and state
    - telemetry.db: Usage metrics and events
    - traces.db: Execution traces for debugging
    """

    def __init__(self, base_path: Path | str):
        self.base_path = Path(base_path).expanduser()
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Database paths
        self.agents_db = self.base_path / "agents.db"
        self.telemetry_db = self.base_path / "telemetry.db"
        self.traces_db = self.base_path / "traces.db"

        # Initialize
        self._init_agents_db()
        self._init_telemetry_db()
        self._init_traces_db()

    # ------------------------------------------------------------------
    # Agents Database
    # ------------------------------------------------------------------

    def _init_agents_db(self):
        """Initialize agents database."""
        with sqlite3.connect(self.agents_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_state (
                    agent_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    last_active REAL NOT NULL,
                    FOREIGN KEY (agent_id) REFERENCES agents(id)
                )
            """)

    def save_agent(self, agent_id: str, name: str, config: dict):
        """Save or update agent configuration."""
        now = time.time()
        with sqlite3.connect(self.agents_db) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO agents (id, name, config, created_at, updated_at)
                   VALUES (?, ?, ?, COALESCE((SELECT created_at FROM agents WHERE id = ?), ?), ?)""",
                (agent_id, name, json.dumps(config), agent_id, now, now)
            )

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get agent configuration."""
        with sqlite3.connect(self.agents_db) as conn:
            row = conn.execute(
                "SELECT name, config, created_at, updated_at FROM agents WHERE id = ?",
                (agent_id,)
            ).fetchone()
            if row:
                return {
                    "id": agent_id,
                    "name": row[0],
                    "config": json.loads(row[1]),
                    "created_at": row[2],
                    "updated_at": row[3],
                }
            return None

    def list_agents(self) -> list[dict]:
        """List all agents."""
        with sqlite3.connect(self.agents_db) as conn:
            rows = conn.execute(
                "SELECT id, name, config, created_at, updated_at FROM agents"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "config": json.loads(r[2]),
                    "created_at": r[3],
                    "updated_at": r[4],
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Telemetry Database
    # ------------------------------------------------------------------

    def _init_telemetry_db(self):
        """Initialize telemetry database."""
        with sqlite3.connect(self.telemetry_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT,
                    data TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp)
            """)

    def log_event(self, event_type: str, data: dict, session_id: str = ""):
        """Log a telemetry event."""
        with sqlite3.connect(self.telemetry_db) as conn:
            conn.execute(
                "INSERT INTO events (event_type, timestamp, session_id, data) VALUES (?, ?, ?, ?)",
                (event_type, time.time(), session_id, json.dumps(data))
            )

    def get_events(
        self,
        event_type: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> list[TelemetryEvent]:
        """Get telemetry events with optional filtering."""
        query = "SELECT event_type, timestamp, session_id, data FROM events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if since:
            query += " AND timestamp > ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.telemetry_db) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                TelemetryEvent(
                    event_type=r[0],
                    timestamp=r[1],
                    session_id=r[2],
                    data=json.loads(r[3]),
                )
                for r in rows
            ]

    def get_stats(self, hours: int = 24) -> dict:
        """Get usage statistics."""
        since = time.time() - (hours * 3600)
        with sqlite3.connect(self.telemetry_db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp > ?",
                (since,)
            ).fetchone()[0]

            by_type = conn.execute(
                "SELECT event_type, COUNT(*) FROM events WHERE timestamp > ? GROUP BY event_type",
                (since,)
            ).fetchall()

            return {
                "total_events": total,
                "hours": hours,
                "by_type": {r[0]: r[1] for r in by_type},
            }

    # ------------------------------------------------------------------
    # Traces Database
    # ------------------------------------------------------------------

    def _init_traces_db(self):
        """Initialize traces database."""
        with sqlite3.connect(self.traces_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    input_data TEXT NOT NULL,
                    output_data TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    timestamp REAL NOT NULL,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_traces_tool ON traces(tool_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_traces_time ON traces(timestamp)
            """)

    def log_trace(
        self,
        trace_id: str,
        tool_name: str,
        input_data: dict,
        output_data: dict,
        success: bool,
        elapsed_ms: float,
        error: Optional[str] = None,
    ):
        """Log an execution trace."""
        with sqlite3.connect(self.traces_db) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, tool_name, input_data, output_data, success, elapsed_ms, timestamp, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    tool_name,
                    json.dumps(input_data),
                    json.dumps(output_data),
                    1 if success else 0,
                    elapsed_ms,
                    time.time(),
                    error,
                )
            )

    def get_traces(
        self,
        tool_name: Optional[str] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> list[ExecutionTrace]:
        """Get execution traces with optional filtering."""
        query = "SELECT * FROM traces WHERE 1=1"
        params = []

        if tool_name:
            query += " AND tool_name = ?"
            params.append(tool_name)
        if success_only:
            query += " AND success = 1"

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.traces_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                ExecutionTrace(
                    trace_id=r["trace_id"],
                    tool_name=r["tool_name"],
                    input_data=json.loads(r["input_data"]),
                    output_data=json.loads(r["output_data"]),
                    success=bool(r["success"]),
                    elapsed_ms=r["elapsed_ms"],
                    timestamp=r["timestamp"],
                    error=r["error"],
                )
                for r in rows
            ]
