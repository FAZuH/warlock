import asyncio

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.model import load_courses
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak


class AutoFill:
    def __init__(self):
        self.conf = Config()
        self.siak = Siak(self.conf)
        self.irs_service = IrsService(self.siak)
        self.courses = load_courses()

    async def start(self):
        await self.siak.start()

        try:
            if self.conf.is_test:
                logger.info("Test mode enabled. Skipping authentication.")
            else:
                logger.info("Navigating to authentication page...")
                await self.siak.page.goto(Path.AUTHENTICATION)

                logger.info("Please authenticate manually in the browser window.")
                logger.info("Waiting for login and role selection...")

                while True:
                    content = await self.siak.content
                    if await self.siak.is_logged_in(content) and await self.siak.is_role_selected(
                        content
                    ):
                        logger.success("Login and role selection detected!")
                        break
                    await asyncio.sleep(1)

            logger.info("Proceeding to fill IRS...")
            if not await self.irs_service.fill_irs(self.courses.copy()):
                return

            await self.irs_service.submit_irs(self.conf.warbot_autosubmit)

            logger.success("AutoFill completed successfully.")
            logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
            # Keep browser open
            while True:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            await self.siak.close()
