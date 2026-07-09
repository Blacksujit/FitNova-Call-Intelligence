"""
Lightweight in-process async task queue for pipeline processing.

Enqueues pipeline tasks and processes them sequentially in a background
thread. Task status is persisted in SQLite so the dashboard can poll it.

Designed for single-process demo scale — swap for Celery + Redis in prod.
"""

import json
import uuid
import time
import logging
import threading
import sqlite3
import os
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

QUEUE_DB = str(Path(__file__).resolve().parent.parent.parent / "fitnova" / "data" / "task_queue.db")

TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"


@dataclass
class Task:
    id: str
    status: str
    endpoint: str
    params: str
    result: str | None
    error: str | None
    created_at: float
    completed_at: float | None


def _init_queue_db():
    os.makedirs(os.path.dirname(QUEUE_DB), exist_ok=True)
    conn = sqlite3.connect(QUEUE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            endpoint TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            result TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            completed_at REAL
        )
    """)
    conn.commit()
    conn.close()


_init_queue_db()


class TaskQueue:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._concurrent_limit = 2
        self._active_count = 0
        self._running = True
        self._cv = threading.Condition(self._lock)
        self._worker = threading.Thread(target=self._process_loop, daemon=True)
        self._worker.start()
        logger.info("Queue worker started (max %d concurrent)", self._concurrent_limit)

    def enqueue(self, endpoint: str, params: str) -> Task:
        task = Task(
            id=uuid.uuid4().hex[:12],
            status=TASK_PENDING,
            endpoint=endpoint,
            params=params,
            result=None,
            error=None,
            created_at=time.time(),
            completed_at=None,
        )
        with self._lock:
            self._tasks[task.id] = task
            self._persist_task(task)
            self._cv.notify()
        logger.info("Enqueued task %s: %s %s", task.id, endpoint, params)
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _persist_task(self, task: Task):
        conn = sqlite3.connect(QUEUE_DB)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (id, status, endpoint, params, result, error, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task.id, task.status, task.endpoint, task.params, task.result, task.error, task.created_at, task.completed_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _process_loop(self):
        while self._running:
            task = None
            with self._lock:
                if self._active_count < self._concurrent_limit:
                    for t in self._tasks.values():
                        if t.status == TASK_PENDING:
                            task = t
                            break
                if task is None:
                    self._cv.wait(timeout=2)
                    continue
                task.status = TASK_RUNNING
                self._persist_task(task)
                self._active_count += 1

            if task:
                try:
                    self._execute_task(task)
                finally:
                    with self._lock:
                        self._active_count -= 1

    def _execute_task(self, task: Task):
        from fitnova.storage.db import get_session
        from fitnova.storage.models import Advisor
        from fitnova.ingestion.folder_source import FolderSource
        from fitnova.pipeline.orchestrator import process_call as run_pipeline

        params = json.loads(task.params) if task.params else {}
        external_call_id = params.get("external_call_id", "")

        db = get_session()
        try:
            source = FolderSource("fitnova/data/incoming")
            calls = source.fetch_new_calls()
            match = None
            for c in calls:
                if c.external_call_id == external_call_id:
                    match = c
                    break

            if not match:
                task.status = TASK_FAILED
                task.error = f"Call {external_call_id} not found in incoming/"
                task.completed_at = time.time()
                with self._lock:
                    self._persist_task(task)
                return

            advisor = db.query(Advisor).filter(Advisor.email == match.advisor_email).first()
            if not advisor:
                task.status = TASK_FAILED
                task.error = f"Advisor with email {match.advisor_email} not found"
                task.completed_at = time.time()
                with self._lock:
                    self._persist_task(task)
                return

            audio_bytes = source.get_audio_bytes(match)
            result = run_pipeline(external_call_id, advisor.id, match.source_type, audio_bytes, db)
            task.status = TASK_DONE
            task.result = json.dumps(result)
            task.completed_at = time.time()
        except Exception as e:
            logger.exception("Task %s failed", task.id)
            task.status = TASK_FAILED
            task.error = str(e)
            task.completed_at = time.time()
        finally:
            db.close()
            with self._lock:
                self._persist_task(task)

    def shutdown(self):
        self._running = False
        with self._lock:
            self._cv.notify_all()
        self._worker.join(timeout=5)


_task_queue = TaskQueue()


def enqueue(endpoint: str, params: str) -> Task:
    return _task_queue.enqueue(endpoint, params)


def get_task(task_id: str) -> Task | None:
    return _task_queue.get_task(task_id)
