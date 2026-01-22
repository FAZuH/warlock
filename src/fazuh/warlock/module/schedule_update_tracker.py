import asyncio
from typing import Dict

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.module.schedule.cache import ScheduleCache
from fazuh.warlock.module.schedule.diff import generate_diff
from fazuh.warlock.module.schedule.notifier import send_notifications
from fazuh.warlock.module.schedule.parser import CourseInfo
from fazuh.warlock.module.schedule.parser import parse_schedule_html
from fazuh.warlock.module.schedule.parser import parse_schedule_string
from fazuh.warlock.module.schedule.parser import serialize_schedule
from fazuh.warlock.siak.siak import Siak


class ScheduleUpdateTracker:
    """Monitors a specific SIAK schedule page for changes.

    Periodically fetches the schedule page, compares it with the previous state,
    and notifies via Discord webhook if any changes (added/removed/modified classes)
    are detected.
    """

    def __init__(self):
        self.conf = Config()
        self.conf.load()

        self.cache = ScheduleCache()
        self.siak = Siak(self.conf)

        # Initialize state
        self._first_run_no_cache = not self.cache.exists()
        if self._first_run_no_cache:
            self.cache.touch()

        self.prev_content = self.cache.read()

    async def start(self):
        """Starts the tracker loop.

        Continuously monitors the schedule at the configured interval.
        """
        try:
            await self.siak.start()

            while True:
                self.conf.load()
                try:
                    if not await self.siak.authenticate():
                        logger.error("Authentication failed.")
                        continue

                    await self.run()
                    logger.success("Schedule update tracker completed successfully.")
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

                logger.info(
                    f"Waiting for the next check in {self.conf.tracker_interval} seconds..."
                )
                await asyncio.sleep(self.conf.tracker_interval)
        finally:
            # Ensure we close browser if loop breaks
            await self.siak.close()

    async def run(self):
        """Executes a single check iteration.

        Fetches the page, parses courses, compares with cache, and sends notifications
        if changes are found.
        """
        # 1. Ensure we are on the right page
        if not await self._ensure_page():
            return

        # 2. Fetch and Parse
        content = await self.siak.page.content()
        new_courses = parse_schedule_html(content)
        curr_str = serialize_schedule(new_courses)

        # 3. Compare
        if self.prev_content == curr_str:
            logger.info("No updates detected.")
            return

        # 4. Handle First Run or Update
        if self._first_run_no_cache:
            await self._handle_first_run(curr_str)
        else:
            await self._handle_update(new_courses, curr_str)

    async def _ensure_page(self) -> bool:
        """Navigates to the tracked URL if needed and verifies login."""
        if self.siak.page.url != self.conf.tracked_url:
            await self.siak.page.goto(self.conf.tracked_url)

        if not await self.siak.is_logged_in_page():
            logger.error("Not logged in. There was an issue in authenticating.")
            return False
        return True

    async def _handle_first_run(self, curr_str: str):
        """Handles the case where no cache existed previously."""
        logger.info("First run with no previous cache. Saving initial state without notification.")
        self.prev_content = curr_str
        await self.cache.write(curr_str)
        self._first_run_no_cache = False

    async def _handle_update(self, new_courses: Dict[str, CourseInfo], curr_str: str):
        """Handles the case where an update is detected."""
        logger.info("Update detected!")

        # Parse old content for diffing
        old_courses = parse_schedule_string(self.prev_content)

        # Generate diff
        changes = generate_diff(
            old_courses,
            new_courses,
            suppress_professor=self.conf.tracker_suppress_professor_change,
            suppress_location=self.conf.tracker_suppress_location_change,
        )

        if not changes:
            logger.info("No meaningful changes detected (only order changed).")
            return

        logger.debug(f"Changes: {changes}")

        # Send notifications
        await send_notifications(
            self.conf.tracker_discord_webhook_url,
            changes,
            self.conf.tracked_url,
            self.conf.tracker_interval,
        )

        # Update state
        self.prev_content = curr_str
        await self.cache.write(curr_str)
