import asyncio
import json
import os
import time

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.siak.siak import Siak
from fazuh.warlock.service.irs_service import IrsService


class WarBot:
    def __init__(self):
        self.conf = Config()
        self.irs_service = IrsService()

        if not os.path.exists("courses.json"):
            logger.error("courses.json file not found. Please create it with the required courses.")
            raise FileNotFoundError("courses.json file not found.")

        with open("courses.json", "r") as f:
            self.courses = json.load(f)

    async def start(self):
        # NOTE: Don't reuse sessions. is_not_registration_period() will always return True until we re-authenticate.
        # This means that the /main/CoursePlan/CoursePlanEdit page WILL NOT update until we logout, then login again
        while True:
            self.siak = Siak(self.conf.username, self.conf.password)
            await self.siak.start()
            self.conf.load()
            try:
                if not await self.siak.authenticate():
                    logger.error("Authentication failed. Is the server down?")
                    continue

                await self.run()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            finally:
                await self.siak.close()
                logger.info(f"Retrying in {self.conf.warbot_interval} seconds...")
                await asyncio.sleep(self.conf.warbot_interval)

    async def run(self):
        # Pass a copy of courses to avoid modifying the original list if we retry
        await self.irs_service.fill_irs(self.siak, self.courses.copy())

        if self.conf.warbot_autosubmit:
            await self.siak.page.click("input[type=submit][value='Simpan IRS']")
            logger.success("IRS saved.")
        else:
            await self.irs_service.scroll_to_bottom(self.siak)

        logger.success("WarBot completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        time.sleep(float("inf"))
