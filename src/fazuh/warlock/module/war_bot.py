import asyncio

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.model import load_courses
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.siak import Siak


class WarBot:
    """Automated bot for aggressive IRS filling (War IRS).

    Continuously attempts to fill the IRS form at a specified interval.
    Designed for high-contention registration periods.
    """

    def __init__(self):
        self.conf = Config()
        self.conf.load()
        self.siak = Siak(self.conf)
        self.irs_service = IrsService(self.siak)
        self.courses = load_courses()

    async def start(self):
        """Starts the WarBot execution loop.

        Continuously authenticates and attempts to fill the IRS.
        If authentication fails or the session expires, it retries.
        """
        # NOTE: Don't reuse sessions. is_not_registration_period() will always return True until we re-authenticate.
        # This means that the /main/CoursePlan/CoursePlanEdit page WILL NOT update until we logout, then login again
        try:
            await self.siak.start()

            while True:
                self.conf.load()
                try:
                    if not await self.siak.authenticate():
                        logger.error("Authentication failed.")
                        continue

                    await self._run()
                    await self.siak.unauthenticate()
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

                logger.info(f"Retrying in {self.conf.warbot_interval} seconds...")
                await asyncio.sleep(self.conf.warbot_interval)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        finally:
            await self.siak.close()

    async def _run(self):
        """Executes a single IRS filling attempt.

        Returns:
            bool: False if filling failed (e.g. registration closed), True otherwise.
        """
        if await self.irs_service.fill_irs(self.courses) is False:
            return False

        await self.irs_service.submit_irs(self.conf.warbot_autosubmit)

        logger.success("WarBot completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        # Keep browser open
        while True:
            await asyncio.sleep(1)
