"""Job runner: polls the backend for pending jobs and processes them.

This is the main entry point for the worker that consumes jobs from the
polling API. It can be run standalone::

    python job_runner.py

or with debug artifacts enabled::

    python job_runner.py --debug
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx

from config import settings
from job_processor import JobProcessor
from logging_config import configure_logging, get_logger

logger = get_logger(__name__)


class JobRunner:
    """Polls the backend and dispatches jobs to a :class:`JobProcessor`."""

    def __init__(
        self,
        base_url: str | None = None,
        poll_interval: int | None = None,
        work_dir: Path | None = None,
    ) -> None:
        """Initialize the runner.

        Args:
            base_url: Backend base URL. Defaults to ``settings.api_url``.
            poll_interval: Polling interval in seconds.
            work_dir: Directory for downloaded assets.
        """
        self.base_url = (base_url or settings.api_url).rstrip("/")
        self.poll_interval = poll_interval or settings.poll_interval
        self.work_dir = work_dir or (settings.output_dir / "jobs")
        self.processor = JobProcessor(self.base_url)

    async def _fetch_next_job(self) -> dict | None:
        """Fetch the next pending job from the backend.

        Returns:
            The job dict, or ``None`` if there are no jobs.
        """
        url = f"{self.base_url}/api/next-job"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        if data.get("status") == "no_jobs":
            return None
        return data

    async def run_forever(self) -> None:
        """Poll for jobs indefinitely and process them as they arrive."""
        logger.info(
            "Job runner started. Polling %s every %ds.",
            self.base_url,
            self.poll_interval,
        )
        while True:
            try:
                job = await self._fetch_next_job()
                if job is None:
                    logger.debug("No jobs pending; sleeping.")
                    await asyncio.sleep(self.poll_interval)
                    continue

                job_id = job["id"]
                logger.info("Processing job %s", job_id)
                try:
                    result = self.processor.process(job_id, self.work_dir)
                    logger.info(
                        "Job %s processed: video=%s", job_id, result["video_path"]
                    )
                    self.processor.notify_completed(job_id)
                except Exception as exc:  # noqa: BLE001 - report failure
                    logger.exception("Job %s failed: %s", job_id, exc)
                    try:
                        self.processor.notify_failed(job_id)
                    except Exception as notify_exc:  # noqa: BLE001
                        logger.error("Could not notify failure: %s", notify_exc)
            except Exception as exc:  # noqa: BLE001 - keep polling alive
                logger.error("Polling error: %s", exc)
                await asyncio.sleep(self.poll_interval)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Polling job runner.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and artifact generation.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process a single job and exit (useful for testing).",
    )
    return parser.parse_args(argv)


async def _run_once(runner: JobRunner) -> None:
    """Process a single job and exit."""
    job = await runner._fetch_next_job()
    if job is None:
        logger.info("No jobs pending.")
        return
    job_id = job["id"]
    logger.info("Processing single job %s", job_id)
    try:
        result = runner.processor.process(job_id, runner.work_dir)
        runner.processor.notify_completed(job_id)
        logger.info("Job %s done: %s", job_id, result["video_path"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed: %s", job_id, exc)
        try:
            runner.processor.notify_failed(job_id)
        except Exception as notify_exc:  # noqa: BLE001
            logger.error("Could not notify failure: %s", notify_exc)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the job runner CLI."""
    args = parse_args(argv)
    configure_logging(debug=args.debug)
    runner = JobRunner()
    if args.once:
        asyncio.run(_run_once(runner))
    else:
        asyncio.run(runner.run_forever())


if __name__ == "__main__":
    main()
