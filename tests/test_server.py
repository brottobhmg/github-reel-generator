"""Tests for the FastAPI backend endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import server


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """Point the DB at a temp file and return a test client."""
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()
    return TestClient(server.app)


def test_next_job_empty(client: TestClient) -> None:
    """next-job returns no_jobs when the queue is empty."""
    response = client.get("/api/next-job")
    assert response.status_code == 200
    assert response.json() == {"status": "no_jobs"}


def test_create_and_claim_job(client: TestClient) -> None:
    """A created job can be claimed via next-job."""
    create = client.post(
        "/api/media",
        json={
            "source_link": "https://github.com/a/b",
            "mp4_path": "/tmp/v.mp4",
            "json_path": "/tmp/d.json",
        },
    )
    assert create.status_code == 200
    job_id = create.json()["job_id"]

    claim = client.get("/api/next-job")
    assert claim.status_code == 200
    assert claim.json()["id"] == job_id
    assert claim.json()["status"] == "processing"


def test_job_completed(client: TestClient) -> None:
    """job-completed marks a job as completed."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    response = client.post(f"/api/job-completed/{job_id}")
    assert response.status_code == 200
    assert db.get_job_by_id(job_id)["status"] == "completed"


def test_job_failed(client: TestClient) -> None:
    """job-failed marks a job as failed."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    response = client.post(f"/api/job-failed/{job_id}")
    assert response.status_code == 200
    assert db.get_job_by_id(job_id)["status"] == "failed"


def test_job_completed_missing(client: TestClient) -> None:
    """job-completed returns 404 for a missing job."""
    response = client.post("/api/job-completed/999")
    assert response.status_code == 404


def test_download_invalid_type(client: TestClient) -> None:
    """download with an invalid file type returns 400."""
    job_id = db.add_job("https://github.com/a/b", "/tmp/v.mp4", "/tmp/d.json")
    response = client.get(f"/api/download/{job_id}/bogus")
    assert response.status_code == 400
