"""Entry point for the Telegram bot pipeline.

Runs the Telegram bot that listens for GitHub links and triggers the media
pipeline. Usage::

    python pipeline.py [--debug]
"""

from __future__ import annotations

import argparse

import db
from logging_config import configure_logging, get_logger
from telegram_bot import run_bot

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Telegram bot pipeline.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and artifact generation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Initialize the database and start the Telegram bot."""
    args = parse_args(argv)
    configure_logging(debug=args.debug)
    db.init_db()
    logger.info("Starting Telegram bot pipeline.")
    run_bot()


if __name__ == "__main__":
    main()
