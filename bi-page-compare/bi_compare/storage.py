from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS templates (
                    name TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    progress_json TEXT NOT NULL,
                    error TEXT,
                    summary_json TEXT,
                    report_json_path TEXT,
                    report_html_path TEXT,
                    config_json TEXT NOT NULL,
                    schedule_id TEXT
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    template_name TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT
                );
                """
            )

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    # -------------------- templates --------------------

    def upsert_template(self, name: str, payload: dict[str, Any]) -> None:
        now = self._now()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM templates WHERE name=?",
                (name,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE templates SET payload_json=?, updated_at=? WHERE name=?",
                    (payload_json, now, name),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO templates(name, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, payload_json, now, now),
                )

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, created_at, updated_at FROM templates ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_template(self, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, payload_json, created_at, updated_at FROM templates WHERE name=?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return {
            "name": row["name"],
            "payload": payload,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def delete_template(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM templates WHERE name=?", (name,))
            return cur.rowcount > 0

    # -------------------- tasks --------------------

    def create_task(self, task_id: str, config_payload: dict[str, Any], *, schedule_id: str | None = None) -> None:
        now = self._now()
        progress = {
            "stage": "queued",
            "message": "Waiting to run",
            "processed_cards": 0,
            "total_cards": 0,
            "processed_page_pairs": 0,
            "total_page_pairs": len(config_payload.get("page_pairs", [])),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                    id, status, created_at, started_at, finished_at,
                    progress_json, error, summary_json, report_json_path,
                    report_html_path, config_json, schedule_id
                ) VALUES (?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (
                    task_id,
                    "queued",
                    now,
                    json.dumps(progress, ensure_ascii=False),
                    json.dumps(config_payload, ensure_ascii=False),
                    schedule_id,
                ),
            )

    def update_task(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return

        updates: list[str] = []
        values: list[Any] = []

        mapping = {
            "status": "status",
            "started_at": "started_at",
            "finished_at": "finished_at",
            "progress": "progress_json",
            "error": "error",
            "summary": "summary_json",
            "report_json_path": "report_json_path",
            "report_html_path": "report_html_path",
        }

        for key, col in mapping.items():
            if key not in fields:
                continue
            val = fields[key]
            if key in {"progress", "summary"} and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            updates.append(f"{col}=?")
            values.append(val)

        if not updates:
            return

        values.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=?"

        with self._connect() as conn:
            conn.execute(sql, values)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_row_to_dict(row)

    def list_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._task_row_to_dict(r) for r in rows if r is not None]

    def _task_row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        progress = json.loads(row["progress_json"]) if row["progress_json"] else {}
        summary = json.loads(row["summary_json"]) if row["summary_json"] else None
        return {
            "id": row["id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "progress": progress,
            "error": row["error"],
            "summary": summary,
            "report_json_path": row["report_json_path"],
            "report_html_path": row["report_html_path"],
            "config": json.loads(row["config_json"]) if row["config_json"] else {},
            "schedule_id": row["schedule_id"],
        }

    # -------------------- schedules --------------------

    def upsert_schedule(
        self,
        *,
        schedule_id: str,
        name: str,
        template_name: str,
        interval_minutes: int,
        enabled: bool,
    ) -> dict[str, Any]:
        now = self._now()
        existing = self.get_schedule(schedule_id)

        if existing is None:
            next_run_at = self._calc_next_run(None, interval_minutes, enabled)
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO schedules(
                        id, name, template_name, interval_minutes, enabled,
                        created_at, updated_at, last_run_at, next_run_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        schedule_id,
                        name,
                        template_name,
                        interval_minutes,
                        1 if enabled else 0,
                        now,
                        now,
                        next_run_at,
                    ),
                )
        else:
            next_run_at = existing.get("next_run_at")
            if not enabled:
                next_run_at = None
            elif not next_run_at:
                next_run_at = self._calc_next_run(existing.get("last_run_at"), interval_minutes, True)

            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE schedules
                    SET name=?, template_name=?, interval_minutes=?, enabled=?,
                        updated_at=?, next_run_at=?
                    WHERE id=?
                    """,
                    (
                        name,
                        template_name,
                        interval_minutes,
                        1 if enabled else 0,
                        now,
                        next_run_at,
                        schedule_id,
                    ),
                )

        schedule = self.get_schedule(schedule_id)
        if schedule is None:
            raise RuntimeError("Failed to save schedule")
        return schedule

    def list_schedules(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        return dict(row) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            return cur.rowcount > 0

    def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            return None

        interval = int(schedule["interval_minutes"])
        next_run_at = None
        if enabled:
            next_run_at = schedule.get("next_run_at") or self._calc_next_run(schedule.get("last_run_at"), interval, True)

        with self._connect() as conn:
            conn.execute(
                "UPDATE schedules SET enabled=?, updated_at=?, next_run_at=? WHERE id=?",
                (1 if enabled else 0, self._now(), next_run_at, schedule_id),
            )
        return self.get_schedule(schedule_id)

    def list_due_schedules(self, now_iso: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM schedules
                WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=?
                ORDER BY next_run_at ASC
                """,
                (now_iso,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_schedule_ran(self, schedule_id: str, *, run_at: str, interval_minutes: int) -> None:
        next_run = self._calc_next_run(run_at, interval_minutes, True)
        with self._connect() as conn:
            conn.execute(
                "UPDATE schedules SET last_run_at=?, next_run_at=?, updated_at=? WHERE id=?",
                (run_at, next_run, self._now(), schedule_id),
            )

    def _calc_next_run(self, base_time: str | None, interval_minutes: int, enabled: bool) -> str | None:
        if not enabled:
            return None
        if interval_minutes <= 0:
            interval_minutes = 60
        if base_time:
            try:
                dt = datetime.fromisoformat(base_time)
            except ValueError:
                dt = datetime.now()
        else:
            dt = datetime.now()
        return (dt + timedelta(minutes=interval_minutes)).isoformat(timespec="seconds")
