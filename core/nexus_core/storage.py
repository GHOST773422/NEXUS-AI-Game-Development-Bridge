"""NEXUS SQLite Storage Manager & Recovery Schema Persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

SQLITE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        engine TEXT NOT NULL,
        root_path TEXT NOT NULL UNIQUE,
        engine_version TEXT,
        status TEXT NOT NULL DEFAULT 'Disconnected',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        engine TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'normal',
        agent_id TEXT NOT NULL DEFAULT 'operator',
        progress INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        current_operation TEXT NOT NULL,
        checkpoint_id TEXT,
        steps_json TEXT NOT NULL,
        logs_json TEXT NOT NULL,
        plan_json TEXT NOT NULL DEFAULT '{}',
        context_json TEXT NOT NULL DEFAULT '{}',
        report_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS checkpoints (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        snapshot_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        outcome TEXT NOT NULL,
        detail_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS daemon_state (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_providers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        model_id TEXT NOT NULL,
        endpoint_url TEXT NOT NULL,
        credential_ref TEXT NOT NULL,
        options_json TEXT NOT NULL DEFAULT '{}',
        is_custom INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS installed_adapters (
        adapter_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        version TEXT NOT NULL,
        engine_kind TEXT NOT NULL,
        runtime_language TEXT NOT NULL,
        is_test_adapter INTEGER NOT NULL DEFAULT 0,
        manifest_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Installed',
        installed_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS operation_journal (
        task_id TEXT NOT NULL,
        op_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        tool_id TEXT NOT NULL,
        target_resources_json TEXT NOT NULL DEFAULT '[]',
        fingerprint TEXT NOT NULL,
        status TEXT NOT NULL,
        error_code TEXT,
        error_message TEXT,
        reversible INTEGER NOT NULL DEFAULT 0,
        file_changes_json TEXT NOT NULL DEFAULT '[]',
        started_at TEXT NOT NULL,
        finished_at TEXT,
        PRIMARY KEY (task_id, op_id),
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS failed_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        op_id TEXT NOT NULL,
        tool_id TEXT NOT NULL,
        arguments_json TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        error_code TEXT,
        error_message TEXT NOT NULL,
        diagnostics_json TEXT NOT NULL DEFAULT '{}',
        repair_attempted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_checkpoints_task_id ON checkpoints(task_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);",
    "CREATE INDEX IF NOT EXISTS idx_op_journal_task_started ON operation_journal(task_id, started_at ASC);",
    "CREATE INDEX IF NOT EXISTS idx_failed_ops_task_id ON failed_operations(task_id, id ASC);",
)


class SQLiteStorageManager:
    """Thread-safe SQLite persistence manager with async wrappers."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._write_epoch: int = 0

    @property
    def is_initialized(self) -> bool:
        return self._conn is not None

    @property
    def write_epoch(self) -> int:
        return self._write_epoch

    def initialize_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = None
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA cache_size = -16384;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA mmap_size = 67108864;")
            with conn:
                for stmt in SQLITE_SCHEMA_STATEMENTS:
                    conn.execute(stmt)
                existing_cols = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(tasks);").fetchall()
                }
                migrations: tuple[tuple[str, str], ...] = (
                    ("priority", "TEXT NOT NULL DEFAULT 'normal'"),
                    ("agent_id", "TEXT NOT NULL DEFAULT 'operator'"),
                    ("progress", "INTEGER NOT NULL DEFAULT 0"),
                    ("checkpoint_id", "TEXT"),
                    ("plan_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("context_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("report_json", "TEXT"),
                )
                for col_name, col_def in migrations:
                    if col_name not in existing_cols:
                        conn.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};")
            self._write_epoch += 1
            self._conn = conn

    async def initialize(self) -> None:
        await asyncio.to_thread(self.initialize_sync)

    def close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    async def close(self) -> None:
        await asyncio.to_thread(self.close_sync)

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteStorageManager is not initialized.")
        return self._conn

    def execute_sync(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        lead = query.lstrip()
        upper_prefix = lead[:7].upper()
        is_read = (
            upper_prefix.startswith("SELECT")
            or upper_prefix.startswith("WITH")
            or upper_prefix.startswith("EXPLAIN")
        )
        with self._lock:
            conn = self._require_conn()
            if is_read:
                cur = conn.execute(query, params)
                desc = cur.description
                if desc is None:
                    return []
                cols = tuple(d[0] for d in desc)
                rows = cur.fetchall()
                if not rows:
                    return []
                return [dict(zip(cols, row)) for row in rows]
            with conn:
                cur = conn.execute(query, params)
                self._write_epoch += 1
                desc = cur.description
                if desc is None:
                    return []
                cols = tuple(d[0] for d in desc)
                rows = cur.fetchall()
                if not rows:
                    return []
                return [dict(zip(cols, row)) for row in rows]

    async def execute(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.execute_sync, query, params)

    def fetch_tuples_sync(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        with self._lock:
            conn = self._require_conn()
            return conn.execute(query, params).fetchall()

    async def fetch_tuples(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        return await asyncio.to_thread(self.fetch_tuples_sync, query, params)

    def execute_many_reads_sync(
        self, queries: list[tuple[str, tuple[Any, ...]]]
    ) -> list[list[dict[str, Any]]]:
        with self._lock:
            conn = self._require_conn()
            results: list[list[dict[str, Any]]] = []
            for query, params in queries:
                cur = conn.execute(query, params)
                desc = cur.description
                if desc is None:
                    results.append([])
                    continue
                cols = tuple(d[0] for d in desc)
                rows = cur.fetchall()
                results.append([dict(zip(cols, row)) for row in rows] if rows else [])
            return results

    async def execute_many_reads(
        self, queries: list[tuple[str, tuple[Any, ...]]]
    ) -> list[list[dict[str, Any]]]:
        return await asyncio.to_thread(self.execute_many_reads_sync, queries)

    def record_audit_sync(
        self,
        actor: str,
        action: str,
        outcome: str,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.execute_sync(
            """
            INSERT INTO audit_logs (timestamp, actor, action, target, outcome, detail_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                actor,
                action,
                target,
                outcome,
                json.dumps(detail or {}, separators=(",", ":"), ensure_ascii=True),
            ),
        )

    async def record_audit(
        self,
        actor: str,
        action: str,
        outcome: str,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self.record_audit_sync, actor, action, outcome, target, detail
        )

    def integrity_check_sync(self) -> str:
        rows = self.execute_sync("PRAGMA integrity_check;")
        if not rows:
            return "unknown"
        return str(next(iter(rows[0].values())))

    async def integrity_check(self) -> str:
        return await asyncio.to_thread(self.integrity_check_sync)
