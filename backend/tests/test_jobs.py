import time

import pytest
from fastapi import HTTPException

from app.routes.jobs import job_status
from app.services import jobs


def _wait_for(job_id: str, status: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        assert job is not None
        if job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {status}")


def test_job_runs_and_reports_result() -> None:
    job_id = jobs.start_job("test", lambda: {"ok": True})
    job = _wait_for(job_id, "done")
    assert job["result"] == {"ok": True}
    assert job["error"] is None


def test_job_records_errors() -> None:
    def _boom() -> None:
        raise ValueError("nope")

    job_id = jobs.start_job("test", _boom)
    job = _wait_for(job_id, "error")
    assert "nope" in job["error"]


def test_job_status_route_404_for_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        job_status("does-not-exist")
    assert exc.value.status_code == 404
