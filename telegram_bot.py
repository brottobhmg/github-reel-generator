"""Telegram bot that triggers the media pipeline.

Users send a GitHub link; the bot runs the pipeline and replies with the
generated description and video.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import telegram
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from config import settings
from content import GITHUB_REGEX
from logging_config import get_logger
from pipeline_core import run_pipeline

logger = get_logger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text(
        "Hi! Send me a GitHub link and I'll start working on it."
    )


def _ensure_repos_file() -> None:
    """Create the processed-repos file on first run if it does not exist."""
    settings.repos_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings.repos_file.exists():
        settings.repos_file.touch()
        logger.info("Created processed-repos file at %s", settings.repos_file)


def _load_processed_repos() -> list[str]:
    """Load the list of already-processed repository URLs."""
    _ensure_repos_file()
    with open(settings.repos_file, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


def _mark_repo_processed(repo_url: str) -> None:
    """Append a repository URL to the processed list."""
    _ensure_repos_file()
    try:
        with open(settings.repos_file, "a", encoding="utf-8") as f:
            f.write(f"{repo_url}\n")
    except OSError as exc:
        logger.warning("Could not save repo to file: %s", exc)


def _format_description_message(desc_path: str, job_id: int) -> str:
    """Build the human-readable description message from a JSON file."""
    with open(desc_path, "r", encoding="utf-8") as desc_file:
        desc_data = json.load(desc_file)

    tags_str = desc_data.get("tag", "")
    hashtags = []
    if tags_str:
        for t in tags_str.split(","):
            cleaned = t.strip().replace(" ", "")
            if cleaned:
                hashtags.append(f"#{cleaned}")
    hashtags_str = " ".join(hashtags)

    return (
        f"🆔 ID: {job_id}\n\n"
        f"✨ TITLE:\n{desc_data.get('titolo', '')}\n\n"
        f"📝 POST DESCRIPTION:\n{desc_data.get('descrizione_post', '')}\n\n"
        f"🏷️ TAGS:\n{tags_str}\n\n"
        f"🏷️ HASHTAGS:\n{hashtags_str}\n\n"
        f"🎙️ TTS TEXT:\n{desc_data.get('testo_tts', '')}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages containing GitHub links."""
    text = update.message.text
    matches = list(GITHUB_REGEX.finditer(text))

    if not matches:
        await update.message.reply_text(
            "I couldn't find any valid GitHub link in this message."
        )
        return

    for match in matches:
        link = match.group(0)
        await update.message.reply_text(
            f"GitHub link detected! Starting processing of: {link}"
        )
        logger.info("Processing link: %s", link)

        if link in _load_processed_repos():
            await update.message.reply_text("Link already processed in the past! ❌")
            continue

        try:
            result = await run_pipeline(link)
            _mark_repo_processed(link)

            job_id = None
            try:
                abs_video = os.path.abspath(result["video_path"])
                abs_desc = os.path.abspath(result["description_path"])
                job_id = db.add_job(link, abs_video, abs_desc)
                logger.info("Logged job ID %s to database.", job_id)
            except Exception as exc:  # noqa: BLE001 - non-fatal
                logger.warning("Could not save job to database: %s", exc)

            await update.message.reply_text(result["message"])

            desc_path = result["description_path"]
            if os.path.exists(desc_path):
                try:
                    message = _format_description_message(desc_path, job_id or 0)
                    await update.message.reply_text(message)
                except Exception as exc:  # noqa: BLE001 - non-fatal
                    logger.warning("Error sending description text: %s", exc)

                try:
                    with open(desc_path, "rb") as desc_file:
                        await update.message.reply_document(
                            document=desc_file,
                            filename="descrizione.json",
                            caption="📄 Description and metadata JSON file",
                        )
                except Exception as exc:  # noqa: BLE001 - non-fatal
                    logger.warning("Error sending description file: %s", exc)

            video_path = result["video_path"]
            if os.path.exists(video_path):
                await update.message.reply_text("📤 Sending the reel video... ⏳")
                try:
                    with open(video_path, "rb") as video_file:
                        await update.message.reply_document(
                            document=video_file,
                            filename=f"{result['repo_name']}_reel.mp4",
                            caption=f"🎥 Reel for {result['repo_name']}",
                        )
                except Exception as exc:  # noqa: BLE001 - non-fatal
                    await update.message.reply_text(
                        f"❌ Error sending the video file: {exc}"
                    )

        except Exception as exc:  # noqa: BLE001 - report to user
            logger.exception("Pipeline failed for %s", link)
            await update.message.reply_text(
                f"❌ Error during the pipeline for {link}: {exc}"
            )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Telegram network and API errors."""
    error = context.error
    if isinstance(error, telegram.error.NetworkError):
        logger.warning("NetworkError: %s", error)
    elif isinstance(error, telegram.error.TimedOut):
        logger.warning("TimedOut: %s", error)
    elif isinstance(error, telegram.error.RetryAfter):
        logger.warning("RetryAfter: retry in %s seconds.", error.retry_after)
    elif isinstance(error, telegram.error.Conflict):
        logger.warning("Conflict (another instance running?): %s", error)
    elif isinstance(error, telegram.error.Unauthorized):
        logger.warning("Unauthorized (invalid/revoked token): %s", error)
    else:
        logger.error("Unknown error %s: %s", type(error).__name__, error)

    try:
        with open("bot_errors.log", "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.now().isoformat()}] "
                f"{type(error).__name__}: {error}\n"
            )
    except OSError:
        pass


def run_bot() -> None:
    """Start the Telegram bot in polling mode."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    logger.info("Bot listening (polling)... Press Ctrl+C to stop.")
    application.run_polling()
