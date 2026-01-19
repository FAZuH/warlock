import argparse
import asyncio

from loguru import logger


async def main():
    parser = argparse.ArgumentParser(description="Warlock Bot")
    parser.add_argument(
        "module",
        choices=["track", "war", "autofill"],
        help="Module to run (track, war, or autofill).",
    )
    args = parser.parse_args()

    logger.add("log/{time}.log", rotation="1 day")

    from fazuh.warlock.bot import init_discord_bot

    await init_discord_bot()

    if args.module == "track":
        from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker

        await ScheduleUpdateTracker().start()

    elif args.module == "war":
        from fazuh.warlock.module.war_bot import WarBot

        await WarBot().start()

    elif args.module == "autofill":
        from fazuh.warlock.module.auto_fill import AutoFill

        await AutoFill().start()


def main_sync():
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
