from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any, Callable

# In-memory job registry for long-running operations (layer builds, scenario
# runs). Lets the UI submit work, return immediately, and poll for progress
# instead of blocking on a multi-minute request. Process-local and ephemeral by
# design — jobs do not survive a restart, which is fine for an operator tool.
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def create_job(kind: str) -> str:
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "pending",
            "result": None,
            "error": None,
        }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job is not None else None


def _set(job_id: str, **fields: Any) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def run_job(job_id: str, fn: Callable[[], Any]) -> None:
    """Run ``fn`` on a background thread, recording status and result/error."""

    def _worker() -> None:
        _set(job_id, status="running")
        try:
            _set(job_id, status="done", result=fn())
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as job error
            _set(job_id, status="error", error=str(exc), traceback=traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()


def start_job(kind: str, fn: Callable[[], Any]) -> str:
    """Create a job and start running ``fn`` in the background; return its id."""
    job_id = create_job(kind)
    run_job(job_id, fn)
    return job_id
