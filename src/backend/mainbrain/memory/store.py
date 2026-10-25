from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from mainbrain.contracts.schemas import LearningMetric, ProgressEvent
from mainbrain.core.ids import new_id, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  correlation_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  content TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  metadata TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
  id UNINDEXED,
  source,
  content,
  tokenize='porter'
);

CREATE TABLE IF NOT EXISTS agent_metrics (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS layout_state (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(SCHEMA)
        cur = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                ("1",),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_json(self, table: str, record_id: str, payload: dict[str, Any], **extra: Any) -> None:
        columns = ["id", "payload"]
        values: list[Any] = [record_id, json.dumps(payload, ensure_ascii=False, default=str)]
        for key, value in extra.items():
            columns.append(key)
            values.append(value)
        placeholders = ", ".join("?" for _ in columns)
        col_sql = ", ".join(columns)
        updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "id")
        self._conn.execute(
            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        self._conn.commit()

    def get_json(self, table: str, record_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(f"SELECT payload FROM {table} WHERE id=?", (record_id,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["payload"])

    def add_event(self, event: ProgressEvent) -> None:
        self.save_json(
            "events",
            event.id,
            event.model_dump(mode="json"),
            correlation_id=event.correlation_id,
            created_at=event.timestamp.isoformat(),
        )

    def list_events(self, correlation_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT payload FROM events WHERE correlation_id=? ORDER BY created_at",
            (correlation_id,),
        )
        return [json.loads(r["payload"]) for r in cur.fetchall()]

    def index_knowledge(
        self,
        content: str,
        source: str,
        *,
        verified: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        kid = new_id("know_")
        now = utc_now().isoformat()
        meta = metadata or {}
        self._conn.execute(
            "INSERT INTO knowledge(id, source, content, verified, metadata, created_at) VALUES (?,?,?,?,?,?)",
            (kid, source, content, 1 if verified else 0, json.dumps(meta, ensure_ascii=False), now),
        )
        self._conn.execute(
            "INSERT INTO knowledge_fts(id, source, content) VALUES (?,?,?)",
            (kid, source, content),
        )
        self._conn.commit()
        return kid

    @staticmethod
    def _fts_query(query: str) -> str | None:
        """SQLite FTS5 — tikai droši tokeni (citādi MATCH krīt un mācīšanās «pazūd»)."""
        import re

        tokens = re.findall(r"[A-Za-z0-9ĀČĒĢĪĶĻŅŠŪŽāčēģīķļņšūž]{2,}", query or "", flags=re.UNICODE)
        if not tokens:
            return None
        # OR + quoted — labāka atbilstība īsiem LV vārdiem
        return " OR ".join(f'"{t}"' for t in tokens[:12])

    def search_knowledge(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        fts = self._fts_query(query)
        if not fts:
            return []
        try:
            cur = self._conn.execute(
                """
                SELECT k.id, k.source, k.content, k.verified, k.metadata, k.created_at
                FROM knowledge_fts f
                JOIN knowledge k ON k.id = f.id
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts, limit),
            )
        except Exception:  # noqa: BLE001 — bojāts MATCH
            return []
        rows = []
        for row in cur.fetchall():
            rows.append(
                {
                    "id": row["id"],
                    "source": row["source"],
                    "content": row["content"],
                    "verified": bool(row["verified"]),
                    "metadata": json.loads(row["metadata"]),
                    "created_at": row["created_at"],
                }
            )
        return rows

    def upsert_metric(self, metric: LearningMetric) -> None:
        self.save_json(
            "agent_metrics",
            metric.agent_id,
            metric.model_dump(mode="json"),
            updated_at=metric.updated_at.isoformat(),
        )

    def list_metrics(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT payload FROM agent_metrics")
        return [json.loads(r["payload"]) for r in cur.fetchall()]

    def save_layout(self, layout_id: str, payload: dict[str, Any]) -> None:
        self.save_json(
            "layout_state",
            layout_id,
            payload,
            updated_at=utc_now().isoformat(),
        )

    def get_layout(self, layout_id: str = "default") -> dict[str, Any] | None:
        return self.get_json("layout_state", layout_id)

    def export_all(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "goals": self._dump_table("goals"),
            "plans": self._dump_table("plans"),
            "tasks": self._dump_table("tasks"),
            "knowledge": self._dump_table("knowledge"),
            "metrics": self.list_metrics(),
        }
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _dump_table(self, table: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(f"SELECT payload FROM {table}")
        return [json.loads(r["payload"]) for r in cur.fetchall()]
