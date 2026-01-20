from loguru import logger

from fazuh.warlock.model import CourseTarget
from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak


class IrsService:
    """Service for handling IRS (Isian Rencana Studi) operations.

    Encapsulates the logic for navigating to the course plan page,
    selecting courses based on configuration, and submitting the plan.
    """

    def __init__(self, siak: Siak) -> None:
        self.siak = siak

    async def fill_irs(self, courses: list[CourseTarget]) -> bool:
        """Navigates to the Course Plan Edit page and fills the IRS form.

        Iterates through the available courses on the page and selects those
        that match the provided targets.

        Args:
            courses: List of CourseTarget objects to select.

        Returns:
            bool: True if navigation and selection process completed (even if some courses weren't found),
                  False if navigation failed or registration is closed.
        """
        await self.siak.page.goto(Path.COURSE_PLAN_EDIT, wait_until="domcontentloaded")

        if self.siak.page.url != Path.COURSE_PLAN_EDIT:
            logger.error(f"Expected {Path.COURSE_PLAN_EDIT}. Found {self.siak.page.url} instead.")
            return False

        if await self.siak.is_not_registration_period():
            logger.error(
                "You cannot fill out the IRS because the academic registration period has not started."
            )
            return False

        logger.info("Navigated to the Course Plan Edit page.")

        # Make a copy of courses to track which ones are found
        pending_courses = courses.copy()

        rows = await self.siak.page.query_selector_all("tr")
        for row in rows:
            if not pending_courses:
                break

            course_element = await row.query_selector("label")
            prof_element = await row.query_selector("td:nth-child(9)")
            time_element = await row.query_selector("td:nth-child(7)")
            radio_element = await row.query_selector('input[type="radio"]')

            if not course_element or not prof_element or not time_element or not radio_element:
                continue

            row_data = {
                "name": await course_element.inner_text(),
                "prof": await prof_element.inner_text(),
                "time": await time_element.inner_text(),
                "code": await radio_element.get_attribute("value") or "",
            }

            # Iterate over a copy of the list so we can modify pending_courses safely
            # Note: We iterate over list(pending_courses) copy, but remove from original pending_courses
            for target in list(pending_courses):
                if target.matches(row_data):
                    await radio_element.check()
                    logger.info(f"Selected: {target} -> {row_data['name']}")

                    if target in pending_courses:
                        pending_courses.remove(target)
                        if not pending_courses:
                            break
                    break

        logger.info("Finished selecting courses")
        for target in pending_courses:
            logger.error(f"Course not found: {target}")

        return True

    async def scroll_to_bottom(self):
        """Scrolls the page to the bottom to ensure all elements are visible."""
        await self.siak.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    async def submit_irs(self, autosubmit: bool = False):
        """Submits the IRS form.

        Args:
            autosubmit: If True, clicks the submit button. If False, only scrolls to bottom.
        """
        if autosubmit:
            await self.siak.page.click("input[type=submit][value='Simpan IRS']")
            logger.success("IRS saved.")
        else:
            await self.scroll_to_bottom()
