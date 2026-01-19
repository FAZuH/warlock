import asyncio
import json
import os
import time

from loguru import logger

from fazuh.warlock.config import Config
from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak


class WarBot:
    def __init__(self):
        self.conf = Config()

        if not os.path.exists("courses.json"):
            logger.error("courses.json file not found. Please create it with the required courses.")
            raise FileNotFoundError("courses.json file not found.")

        with open("courses.json", "r") as f:
            self.courses = json.load(f)

    async def start(self):
        # NOTE: Don't reuse sessions. self.is_not_registration_period() will always return True until we re-authenticate.
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
        await self.siak.page.goto(Path.COURSE_PLAN_EDIT, wait_until="domcontentloaded")
        if self.siak.page.url != Path.COURSE_PLAN_EDIT:
            logger.error(f"Expected {Path.COURSE_PLAN_EDIT}. Found {self.siak.page.url} instead.")
            return
        if await self.is_not_registration_period():
            logger.error(
                "You cannot fill out the IRS because the academic registration period has not started."
            )
            return

        logger.success("Successfully navigated to the Course Plan Edit page.")
        rows = await self.siak.page.query_selector_all("tr")
        for row in rows:
            course_element = await row.query_selector("label")
            prof_element = await row.query_selector("td:nth-child(9)")
            if not course_element or not prof_element:
                continue

            course = await course_element.inner_text()
            prof = await prof_element.inner_text()

            for key, val in self.courses.items():
                if key.lower() not in course.lower() or val.lower() not in prof.lower():
                    continue

                button = await row.query_selector('input[type="radio"]')
                if not button:
                    continue

                await button.check()
                logger.info(f"Selected course: {course} with prof: {prof}")
                del self.courses[key]
                break

        logger.info("Finished selecting courses")
        for key, val in self.courses.items():
            logger.error(f"Course not found: {key} with prof: {val}")

        if self.conf.warbot_autosubmit:
            await self.siak.page.click("input[type=submit][value='Simpan IRS']")
            logger.success("IRS saved.")
        else:
            await self.siak.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        logger.success("WarBot completed successfully.")
        logger.info("Script finished. Press Ctrl+C to exit (including the browser).")
        time.sleep(float("inf"))

    async def is_not_registration_period(self) -> bool:
        """Check if the current period is not a registration period."""
        content = await self.siak.page.content()
        return (
            "Anda tidak dapat mengisi IRS karena periode registrasi akademik belum dimulai"
            in content
        )
