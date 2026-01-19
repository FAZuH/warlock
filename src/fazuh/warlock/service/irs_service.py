from loguru import logger

from fazuh.warlock.siak.path import Path
from fazuh.warlock.siak.siak import Siak


class IrsService:
    async def fill_irs(self, siak: Siak, courses: dict[str, str]) -> bool:
        """Navigates to the Course Plan Edit page and fills the IRS form."""
        await siak.page.goto(Path.COURSE_PLAN_EDIT, wait_until="domcontentloaded")

        if siak.page.url != Path.COURSE_PLAN_EDIT:
            logger.error(f"Expected {Path.COURSE_PLAN_EDIT}. Found {siak.page.url} instead.")
            return False

        if await siak.is_not_registration_period():
            logger.error(
                "You cannot fill out the IRS because the academic registration period has not started."
            )
            return False

        logger.success("Successfully navigated to the Course Plan Edit page.")

        # Make a copy of courses to track which ones are found
        pending_courses = courses.copy()

        rows = await siak.page.query_selector_all("tr")
        for row in rows:
            course_element = await row.query_selector("label")
            prof_element = await row.query_selector("td:nth-child(9)")
            if not course_element or not prof_element:
                continue

            course_text = await course_element.inner_text()
            prof_text = await prof_element.inner_text()

            # Iterate over a copy of keys so we can modify the pending_courses dict if needed
            # (though here we just want to find a match)
            for key, val in list(pending_courses.items()):
                if key.lower() in course_text.lower() and val.lower() in prof_text.lower():
                    button = await row.query_selector('input[type="radio"]')
                    if not button:
                        continue

                    await button.check()
                    logger.info(f"Selected course: {course_text} with prof: {prof_text}")
                    # Remove from pending list
                    if key in pending_courses:
                        del pending_courses[key]
                    break

        logger.info("Finished selecting courses")
        for key, val in pending_courses.items():
            logger.error(f"Course not found: {key} with prof: {val}")

        return True

    async def scroll_to_bottom(self, siak: Siak):
        await siak.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
