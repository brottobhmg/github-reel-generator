"""FastAPI backend for the media automation polling API.

Implements the server side of the polling contract: a job queue with
``/api/next-job``, file download endpoints and completion/failure callbacks.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db
from logging_config import configure_logging, get_logger

logger = get_logger(__name__)

app = FastAPI(title="Media Automation API")

# Initialize database on startup.
db.init_db()


class MediaJobInput(BaseModel):
    """Payload for creating a new media job."""

    source_link: str
    mp4_path: str
    json_path: str


@app.post("/api/media")
def create_media_job(job: MediaJobInput) -> dict:
    """Create a new media job.

    Args:
        job: The job payload.

    Returns:
        A dict with ``status`` and ``job_id``.
    """
    try:
        job_id = db.add_job(job.source_link, job.mp4_path, job.json_path)
        logger.info("Created job %s for %s", job_id, job.source_link)
        return {"status": "success", "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create job.")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/next-job")
def get_next_job() -> dict:
    """Return the next pending job, or ``{"status": "no_jobs"}``."""
    try:
        job = db.get_next_job()
        if job:
            logger.info("Dispatching job %s", job["id"])
            return {
                "id": job["id"],
                "source_link": job["source_link"],
                "mp4_path": job["mp4_path"],
                "json_path": job["json_path"],
                "status": "processing",
            }
        return {"status": "no_jobs"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch next job.")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/download/{job_id}/{file_type}")
def download_file(job_id: int, file_type: str):
    """Serve the video or JSON file associated with a job.

    Args:
        job_id: The job identifier.
        file_type: Either ``video`` or ``json``.

    Returns:
        A :class:`FileResponse` with the requested file.
    """
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if file_type == "video":
        path = job["mp4_path"]
    elif file_type == "json":
        path = job["json_path"]
    else:
        raise HTTPException(
            status_code=400, detail="Invalid file type. Must be 'video' or 'json'"
        )

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return FileResponse(path)


@app.post("/api/job-completed/{job_id}")
def job_completed(job_id: int) -> dict:
    """Mark a job as completed.

    Args:
        job_id: The job identifier.

    Returns:
        A confirmation dict.
    """
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.update_job_status(job_id, "completed")
    logger.info("Job %s marked completed.", job_id)
    return {"status": "success", "message": f"Job {job_id} completed"}


@app.post("/api/job-failed/{job_id}")
def job_failed(job_id: int) -> dict:
    """Mark a job as failed.

    Args:
        job_id: The job identifier.

    Returns:
        A confirmation dict.
    """
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.update_job_status(job_id, "failed")
    logger.info("Job %s marked failed.", job_id)
    return {"status": "success", "message": f"Job {job_id} failed"}


configure_logging()
