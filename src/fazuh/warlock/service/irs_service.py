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

    async def fill_irs(self, courses: list[CourseTarget], false_on_notfound: bool = False) -> bool:
        """Navigates to the Course Plan Edit page and fills the IRS form.

        Iterates through the available courses on the page and selects those
        that match the provided targets.

        Args:
            courses: List of CourseTarget objects to select.
            false_on_notfound: Returns False when there are courses not found in IRS page.

        Returns:
            bool: True if navigation and selection process completed (even if some courses weren't found),
                  False if navigation failed, registration is closed, or a course is not found when false_on_notfound is true.
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

        # Extract all row data in one go to avoid N+1 round-trips
        rows_data = await self.siak.page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('tr'));
                return rows.map(row => {
                    const courseEl = row.querySelector('label');
                    const profEl = row.querySelector('td:nth-child(9)');
                    const timeEl = row.querySelector('td:nth-child(7)');
                    const radioEl = row.querySelector('input[type="radio"]');
                    
                    if (!courseEl || !profEl || !timeEl || !radioEl) {
                        return null;
                    }
                    
                    return {
                        name: courseEl.innerText,
                        prof: profEl.innerText,
                        time: timeEl.innerText,
                        code: radioEl.value
                    };
                }).filter(item => item !== null);
            }
        """)

        for row_data in rows_data:
            if not pending_courses:
                break

            # Iterate over a copy of the list so we can modify pending_courses safely
            for target in list(pending_courses):
                if target.matches(row_data):
                    # Check the radio button using its value
                    await self.siak.page.check(f'input[type="radio"][value="{row_data["code"]}"]')
                    logger.info(f"Selected: {target} -> {row_data['name']}")

                    if target in pending_courses:
                        pending_courses.remove(target)
                    break

        logger.info("Finished selecting courses")
        for target in pending_courses:
            logger.error(f"Course not found: {target}")
            if false_on_notfound:
                return False

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
