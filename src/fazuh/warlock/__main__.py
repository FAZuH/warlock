"""Main entry point for the Warlock application.

Handles command-line argument parsing and dispatches execution to the
requested module (track, war, or autofill).
"""

import argparse
import asyncio

from loguru import logger

from fazuh.warlock.config import Config


async def main():
    """Async entry point.

    Parses arguments, initializes configuration and logging, sets up the
    Discord bot, and runs the selected module.
    """
    parser = argparse.ArgumentParser(description="Warlock Bot")
    parser.add_argument(
        "module",
        choices=["track", "war", "autofill"],
        help="Module to run (track, war, or autofill).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Enable test mode with mocking",
    )
    parser.add_argument(
        "--jadwal-html",
        type=str,
        help="Path to Jadwal HTML for mocking",
    )
    args = parser.parse_args()

    conf = Config()
    conf.is_test = args.test
    conf.jadwal_html_path = args.jadwal_html

    logger.add("log/{time}.log", rotation="1 day")

    from fazuh.warlock.bot import init_discord_bot

    # NOTE: Early async bot initialization. on_ready state will be awaited when needed.
    init_discord_bot()

    try:
        if args.module == "track":
            from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker

            await ScheduleUpdateTracker().start()

        elif args.module == "war":
            from fazuh.warlock.module.war_bot import WarBot

            await WarBot().start()

        elif args.module == "autofill":
            from fazuh.warlock.module.auto_fill import AutoFill

            await AutoFill().start()
    except Exception as e:
        logger.error(e)


def main_sync():
    """Synchronous wrapper for the async main function."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
