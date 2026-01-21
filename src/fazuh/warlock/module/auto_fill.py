import asyncio

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.model import load_courses
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak


class AutoFill:
    """Automated tool for one-time IRS filling.

    Unlike WarBot, this is designed for a single, user-initiated fill operation.
    It supports manual authentication in the browser window.
    """

    def __init__(self):
        self.conf = Config()
        self.conf.load()
        self.siak = Siak(self.conf)
        self.irs_service = IrsService(self.siak)
        self.courses = load_courses()

    async def start(self):
        """Starts the AutoFill process.

        Launches the browser, handles authentication, and proceeds to fill the IRS.
        """
        try:
            await self.siak.start()
            await self._auth()
            await self._run()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        finally:
            await self.siak.close()

    async def _run(self):
        """Executes the IRS filling logic."""
        logger.info("Proceeding to fill IRS...")
        if not await self.irs_service.fill_irs(self.courses):
            return

        await self.irs_service.submit_irs(self.conf.warbot_autosubmit)

        logger.success("AutoFill completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        # Keep browser open
        while True:
            await asyncio.sleep(1)

    async def _auth(self):
        """Handles the authentication process.

        Navigates to the login page and waits for the user to manually log in
        and select a role.
        """
        logger.info("Navigating to authentication page...")
        await self.siak.page.goto(Path.AUTHENTICATION)

        logger.info("Please authenticate manually in the browser window.")
        logger.info("Waiting for login and role selection...")

        while True:
            content = await self.siak.content
            if await self.siak.is_logged_in_page(content) and await self.siak.is_role_selected(
                content
            ):
                logger.info("Login and role selection detected!")
                break
            await asyncio.sleep(1)
