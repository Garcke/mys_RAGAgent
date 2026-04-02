import threading
import time

_ingest_tasks: dict[str, dict] = {}
_ingest_tasks_lock = threading.Lock()


def set_ingest_task(task_id: str, payload: dict):
    with _ingest_tasks_lock:
        if task_id not in _ingest_tasks:
            _ingest_tasks[task_id] = {}
        _ingest_tasks[task_id].update(payload)
        _ingest_tasks[task_id]["updated_at"] = int(time.time())


def get_ingest_task(task_id: str) -> dict | None:
    with _ingest_tasks_lock:
        task = _ingest_tasks.get(task_id)
        return dict(task) if task else None
