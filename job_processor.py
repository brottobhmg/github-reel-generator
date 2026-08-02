"""Job processor: downloads and processes a single job from the backend.

Implements the client side of the polling API contract (see
``docs/ARCHITECTURE.md``): downloads the video and JSON metadata for a job and
notifies the server of success or failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)

#: Timeouts (seconds) for each API call.
VIDEO_TIMEOUT = 30.0
JSON_TIMEOUT = 10.0
NOTIFY_TIMEOUT = 10.0


class JobProcessor:
    """Processes a single job by downloading its assets from the backend."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the processor.

        Args:
            base_url: Backend base URL. Defaults to ``settings.api_url``.
        """
        self.base_url = (base_url or settings.api_url).rstrip("/")

    def download_video(self, job_id: int, dest_dir: Path) -> Path:
        """Download the video for a job.

        Args:
            job_id: The job identifier.
            dest_dir: Directory where the video is saved.

        Returns:
            The path of the downloaded video file.
        """
        url = f"{self.base_url}/api/download/{job_id}/video"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"job_{job_id}.mp4"
        with httpx.stream("GET", url, timeout=VIDEO_TIMEOUT) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        logger.info("Downloaded video for job %s to %s", job_id, dest)
        return dest

    def download_json(self, job_id: int) -> dict:
        """Download the JSON metadata for a job.

        Args:
            job_id: The job identifier.

        Returns:
            The parsed metadata dictionary.
        """
        url = f"{self.base_url}/api/download/{job_id}/json"
        response = httpx.get(url, timeout=JSON_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        logger.info("Downloaded JSON metadata for job %s", job_id)
        return data

    def notify_completed(self, job_id: int) -> None:
        """Notify the server that a job completed successfully.

        Args:
            job_id: The job identifier.
        """
        url = f"{self.base_url}/api/job-completed/{job_id}"
        response = httpx.post(url, timeout=NOTIFY_TIMEOUT)
        response.raise_for_status()
        logger.info("Notified server: job %s completed.", job_id)

    def notify_failed(self, job_id: int) -> None:
        """Notify the server that a job failed.

        Args:
            job_id: The job identifier.
        """
        url = f"{self.base_url}/api/job-failed/{job_id}"
        response = httpx.post(url, timeout=NOTIFY_TIMEOUT)
        response.raise_for_status()
        logger.info("Notified server: job %s failed.", job_id)

    def process(self, job_id: int, dest_dir: Path) -> dict:
        """Download and process a job's assets.

        Args:
            job_id: The job identifier.
            dest_dir: Directory where downloaded assets are saved.

        Returns:
            A dict with ``video_path`` and ``metadata``.
        """
        video_path = self.download_video(job_id, dest_dir)
        metadata = self.download_json(job_id)
        return {"video_path": video_path, "metadata": metadata}
