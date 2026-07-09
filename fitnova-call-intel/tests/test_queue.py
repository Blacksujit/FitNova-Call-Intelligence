"""Tests for the background task queue."""

import time
import json
from fitnova.api import queue as tq


class TestTaskQueue:
    def test_enqueue_returns_task_with_id(self):
        task = tq.enqueue("process_call", json.dumps({"external_call_id": "T"}))
        assert task.id is not None
        assert len(task.id) == 12

    def test_get_task_returns_same(self):
        task = tq.enqueue("process_call", json.dumps({"external_call_id": "X"}))
        fetched = tq.get_task(task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_get_nonexistent_returns_none(self):
        assert tq.get_task("DOES_NOT_EXIST") is None

    def test_initial_status_is_pending(self):
        task = tq.enqueue("process_call", json.dumps({"external_call_id": "Y"}))
        assert task.status == "pending"

    def test_multiple_tasks_get_unique_ids(self):
        t1 = tq.enqueue("a", "{}")
        t2 = tq.enqueue("b", "{}")
        assert t1.id != t2.id
