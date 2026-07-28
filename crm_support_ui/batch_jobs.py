from __future__ import annotations

import csv
import io
import sqlite3
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


TERMINAL_ITEM_STATUSES = {"succeeded", "failed"}


def parse_excel_tsv(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    rows = [[cell.strip() for cell in row] for row in reader]
    return [row for row in rows if any(row)]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BatchJobStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS batch_items (
                    item_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    client_key TEXT NOT NULL,
                    source_entity TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    actual_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_id TEXT NOT NULL DEFAULT '',
                    record_url TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS batch_items_job_position
                    ON batch_items(job_id, position);
                """
            )

    def create_job(self, items: list[dict]) -> dict:
        if not items:
            raise ValueError("A batch job needs at least one item")
        job_id = str(uuid.uuid4())
        timestamp = _now()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO batch_jobs(id, created_at, updated_at) VALUES (?, ?, ?)",
                (job_id, timestamp, timestamp),
            )
            connection.executemany(
                """
                INSERT INTO batch_items(
                    item_id, job_id, position, client_key, source_entity, source_id,
                    source_name, subject, description, actual_end, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                [
                    (
                        str(uuid.uuid4()),
                        job_id,
                        position,
                        str(item["client_key"]),
                        str(item["source_entity"]),
                        str(item["source_id"]),
                        str(item.get("source_name") or ""),
                        str(item["subject"]).strip(),
                        str(item.get("description") or "").strip(),
                        str(item["actual_end"]).strip(),
                    )
                    for position, item in enumerate(items)
                ],
            )
        return self.get_job(job_id)

    def pending_items(self, job_id: str) -> list[dict]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM batch_items WHERE job_id = ? AND status = 'pending' "
                "ORDER BY position",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recover_incomplete_jobs(self) -> list[str]:
        with self._session() as connection:
            connection.execute(
                "UPDATE batch_items SET status = 'pending' WHERE status = 'running'"
            )
            rows = connection.execute(
                "SELECT DISTINCT job_id FROM batch_items WHERE status = 'pending'"
            ).fetchall()
        return [str(row["job_id"]) for row in rows]

    def mark_item_running(self, item_id: str) -> None:
        self._update_item(item_id, "running")

    def mark_item_succeeded(self, item_id: str, record_id: str, record_url: str) -> None:
        self._update_item(
            item_id,
            "succeeded",
            record_id=record_id,
            record_url=record_url,
            error="",
        )

    def mark_item_failed(self, item_id: str, error: str) -> None:
        self._update_item(item_id, "failed", error=error[:2000])

    def _update_item(self, item_id: str, status: str, **values: str) -> None:
        assignments = ["status = ?"]
        parameters: list[str] = [status]
        for column in ("record_id", "record_url", "error"):
            if column in values:
                assignments.append(f"{column} = ?")
                parameters.append(values[column])
        parameters.append(item_id)
        with self._session() as connection:
            connection.execute(
                f"UPDATE batch_items SET {', '.join(assignments)} WHERE item_id = ?",
                parameters,
            )
            connection.execute(
                "UPDATE batch_jobs SET updated_at = ? WHERE id = "
                "(SELECT job_id FROM batch_items WHERE item_id = ?)",
                (_now(), item_id),
            )

    def get_job(self, job_id: str) -> dict:
        with self._session() as connection:
            job_row = connection.execute(
                "SELECT * FROM batch_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise KeyError(job_id)
            item_rows = connection.execute(
                "SELECT * FROM batch_items WHERE job_id = ? ORDER BY position",
                (job_id,),
            ).fetchall()

        items = [dict(row) for row in item_rows]
        succeeded = sum(item["status"] == "succeeded" for item in items)
        failed = sum(item["status"] == "failed" for item in items)
        completed = succeeded + failed
        if completed == len(items):
            status = "completed"
        elif any(item["status"] != "pending" for item in items):
            status = "running"
        else:
            status = "queued"
        return {
            "id": job_id,
            "created_at": job_row["created_at"],
            "updated_at": job_row["updated_at"],
            "status": status,
            "total": len(items),
            "completed": completed,
            "succeeded": succeeded,
            "failed": failed,
            "items": items,
        }


class BatchJobManager:
    def __init__(self, store: BatchJobStore, gateway, recover: bool = True) -> None:
        self.store = store
        self.gateway = gateway
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crm-batch")
        if recover:
            for job_id in self.store.recover_incomplete_jobs():
                self._schedule(job_id)

    def create_job(self, items: list[dict]) -> dict:
        job = self.store.create_job(items)
        self._schedule(job["id"])
        return job

    def get_job(self, job_id: str) -> dict:
        return self.store.get_job(job_id)

    def _schedule(self, job_id: str) -> None:
        self._executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: str) -> None:
        items = self.store.pending_items(job_id)
        if not items:
            return
        self.gateway.run_batch(
            items,
            on_start=lambda item: self.store.mark_item_running(item["item_id"]),
            on_success=lambda item, result: self.store.mark_item_succeeded(
                item["item_id"], result["id"], result["url"]
            ),
            on_failure=lambda item, error: self.store.mark_item_failed(
                item["item_id"], str(error)
            ),
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
