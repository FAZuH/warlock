import asyncio
import json
import os
import time

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak
from fazuh.warlock.service.irs_service import IrsService


class AutoFill:
    def __init__(self):
        self.conf = Config()
        self.irs_service = IrsService()

        if not os.path.exists("courses.json"):
            logger.error("courses.json file not found. Please create it with the required courses.")
            raise FileNotFoundError("courses.json file not found.")

        with open("courses.json", "r") as f:
            self.courses = json.load(f)

    async def start(self):
        # We need credentials for Siak constructor, even if we don't use them for auto-login
        self.siak = Siak(self.conf.username, self.conf.password)
        await self.siak.start()

        try:
            logger.info("Navigating to authentication page...")
            await self.siak.page.goto(Path.AUTHENTICATION)

            logger.info("Please authenticate manually in the browser window.")
            logger.info("Waiting for login and role selection...")

            while True:
                content = await self.siak.content
                if self.siak.is_logged_in(content) and self.siak.is_role_selected(content):
                    logger.success("Login and role selection detected!")
                    break
                await asyncio.sleep(1)

            logger.info("Proceeding to fill IRS...")
            await self.irs_service.fill_irs(self.siak, self.courses.copy())

            await self.irs_service.scroll_to_bottom(self.siak)

            logger.success("AutoFill completed successfully.")
            logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
            # Keep browser open
            while True:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            await self.siak.close()
