import asyncio

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.model import load_courses
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.siak import Siak


class WarBot:
    def __init__(self):
        self.conf = Config()
        self.siak = Siak(self.conf)
        self.irs_service = IrsService(self.siak)
        self.courses = load_courses()

    async def start(self):
        # NOTE: Don't reuse sessions. is_not_registration_period() will always return True until we re-authenticate.
        # This means that the /main/CoursePlan/CoursePlanEdit page WILL NOT update until we logout, then login again
        await self.siak.start()

        try:
            while True:
                self.conf.load()
                try:
                    if not await self.siak.authenticate():
                        logger.error("Authentication failed.")
                        continue

                    await self.run()
                    await self.siak.unauthenticate()
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                finally:
                    logger.info(f"Retrying in {self.conf.warbot_interval} seconds...")
                    await asyncio.sleep(self.conf.warbot_interval)
        finally:
            # Ensure we close browser if loop breaks
            await self.siak.close()

    async def run(self):
        # Pass a copy of courses to avoid modifying the original list if we retry
        if await self.irs_service.fill_irs(self.courses) is False:
            return False

        await self.irs_service.submit_irs(self.conf.warbot_autosubmit)

        logger.success("WarBot completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        # Keep browser open
        while True:
            await asyncio.sleep(1)
