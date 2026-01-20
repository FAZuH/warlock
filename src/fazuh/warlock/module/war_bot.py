import asyncio

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.model import load_courses
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.siak import Siak


class WarBot:
    def __init__(self):
        self.conf = Config()
        self.irs_service = IrsService()
        self.courses = load_courses()

    async def start(self):
        # NOTE: Don't reuse sessions. is_not_registration_period() will always return True until we re-authenticate.
        # This means that the /main/CoursePlan/CoursePlanEdit page WILL NOT update until we logout, then login again
        self.siak = Siak(self.conf)
        await self.siak.start()

        if self.conf.is_test:
            logger.info("Test mode enabled. Skipping authentication.")
        else:
            try:
                while True:
                    self.conf.load()
                    try:
                        if not await self.siak.authenticate():
                            logger.error("Authentication failed. Is the server down?")
                            await self.siak.restart()
                            continue

                        await self.run()
                        await self.siak.unauthenticate()
                    except Exception as e:
                        logger.error(f"An error occurred: {e}")
                    finally:
                        # Instead of closing browser, just logout
                        logger.info(f"Retrying in {self.conf.warbot_interval} seconds...")
                        await asyncio.sleep(self.conf.warbot_interval)
            finally:
                # Ensure we close browser if loop breaks
                await self.siak.close()

    async def run(self):
        # Pass a copy of courses to avoid modifying the original list if we retry
        if await self.irs_service.fill_irs(self.siak, self.courses) is False:
            return False

        if self.conf.warbot_autosubmit:
            await self.siak.page.click("input[type=submit][value='Simpan IRS']")
            logger.success("IRS saved.")
        else:
            await self.irs_service.scroll_to_bottom(self.siak)

        logger.success("WarBot completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        # Keep browser open
        while True:
            await asyncio.sleep(1)
