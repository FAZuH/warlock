from pathlib import Path
import re
from typing import Optional, Union

from bs4 import BeautifulSoup
from bs4 import Tag
from loguru import logger
from playwright.async_api import Page
from playwright.async_api import Route


class MockManager:
    """Manages test environment setup and mocking.

    This class is responsible for configuring the Playwright environment for testing,
    including intercepting network requests and serving mock HTML content for
    SIAK pages.
    """

    def __init__(self, schedule_html_path: Union[str, Path], tracked_url: Optional[str] = None):
        self.schedule_html_path = Path(schedule_html_path)
        self.tracked_url = tracked_url
        self.tests_dir = Path("tests")
        # Ensure we use absolute path relative to cwd if needed, or rely on cwd being project root
        self.template_path = self.tests_dir / "mock" / "irs_page.html"

    async def setup_mocks(self, page: Page):
        """Sets up network mocks for the Playwright page.

        Intercepts requests to SIAK URLs and serves mock content based on
        local HTML templates and configuration. This allows testing without
        hitting the actual SIAK servers.

        Args:
            page: The Playwright Page object to configure.
        """
        logger.info("Setting up mocks...")

        # Intercept Tracked URL (Jadwal)
        if self.schedule_html_path.exists():
            jadwal_content = self.schedule_html_path.read_text(encoding="utf-8", errors="ignore")

            # Mock the tracked URL (for ScheduleUpdateTracker)
            if self.tracked_url:
                await page.route(
                    self.tracked_url,
                    lambda route: route.fulfill(
                        status=200, content_type="text/html", body=jadwal_content
                    ),
                )
        else:
            logger.error(f"Jadwal HTML not found at {self.schedule_html_path}")

        # Intercept IRS Page (WarBot/AutoFill)
        async def handle_irs(route: Route):
            try:
                html = self._generate_irs_html()
                await route.fulfill(status=200, content_type="text/html", body=html)
            except Exception as e:
                logger.error(f"Failed to generate mock IRS: {e}")
                await route.continue_()

        # Use glob pattern instead of importing SiakPath to avoid dependency issues
        await page.route("**/CoursePlan/CoursePlanEdit", handle_irs)

        # Mock submission
        await page.route(
            "**/CoursePlanSave",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body>IRS Saved Mock</body></html>",
            ),
        )

    def _generate_irs_html(self) -> str:
        """Generates a mock IRS page HTML.

        Constructs a mock IRS (Course Plan) page by injecting course data
        parsed from the schedule (jadwal) HTML into a template.

        Returns:
            str: The generated HTML content for the IRS page.
        """
        if not self.schedule_html_path.exists():
            return ""

        jadwal_soup = BeautifulSoup(
            self.schedule_html_path.read_text(encoding="utf-8", errors="ignore"), "html.parser"
        )

        if not self.template_path.exists():
            logger.error(f"Template not found at {self.template_path}")
            return ""

        template_soup = BeautifulSoup(
            self.template_path.read_text(encoding="utf-8", errors="ignore"), "html.parser"
        )

        target_table = None
        for table in template_soup.find_all("table", class_="box"):
            if isinstance(table, Tag) and table.find("th", string=re.compile("Mata Kuliah")):
                target_table = table
                break

        if not target_table:
            logger.error("Could not find target table in IRS template")
            return str(template_soup)

        tbody = target_table.find("tbody")
        if not tbody:
            tbody = target_table

        if not isinstance(tbody, Tag):
            return str(template_soup)

        # Keep the header row(s)
        rows_to_keep = []
        for row in tbody.find_all("tr", recursive=False):
            if isinstance(row, Tag) and row.find("th", string=re.compile("Mata Kuliah")):
                rows_to_keep.append(row)

        tbody.clear()
        for row in rows_to_keep:
            tbody.append(row)

        courses = self._parse_jadwal(jadwal_soup)

        row_id_counter = 0

        for course_name, classes in courses.items():
            # Add Course Header
            header_tr = template_soup.new_tag("tr")
            header_th = template_soup.new_tag(
                "th", attrs={"class": "sub border2 pad2", "colspan": "10"}
            )
            header_th.string = course_name
            header_tr.append(header_th)
            tbody.append(header_tr)

            for cls in classes:
                row_tr = template_soup.new_tag(
                    "tr",
                    attrs={
                        "id": f"r{row_id_counter}",
                        "class": "alt" if row_id_counter % 2 == 0 else "x",
                    },
                )

                # 1. Radio
                td_radio = template_soup.new_tag("td", attrs={"class": "ce"})
                radio_id = f"c{row_id_counter}"
                radio_val = f"MOCK-{row_id_counter}"

                # Try to extract a code from course name
                code_match = re.search(r"([A-Z0-9]+)", course_name)
                code = code_match.group(1) if code_match else "MOCK"
                radio_name = f"c[{code}]"

                inp = template_soup.new_tag(
                    "input",
                    attrs={
                        "type": "radio",
                        "id": radio_id,
                        "name": radio_name,
                        "value": radio_val,
                        "onclick": f"selectRow(this, {row_id_counter})",
                    },
                )
                td_radio.append(inp)
                row_tr.append(td_radio)

                # 2. Name
                td_name = template_soup.new_tag("td", attrs={"style": "white-space:normal"})
                lbl = template_soup.new_tag("label", attrs={"for": radio_id})
                lbl.string = cls["name"]
                td_name.append(lbl)
                row_tr.append(td_name)

                # 3. Language
                td_lang = template_soup.new_tag("td")
                td_lang.string = "Indonesia"
                row_tr.append(td_lang)

                # 4. Capacity
                td_cap = template_soup.new_tag("td", attrs={"class": "ri"})
                td_cap.string = "50"
                row_tr.append(td_cap)

                # 5. Enrolled
                td_enr = template_soup.new_tag("td", attrs={"class": "ri"})
                td_enr.string = "0"
                row_tr.append(td_enr)

                # 6. Term
                td_term = template_soup.new_tag("td", attrs={"class": "ce"})
                td_term.string = "1"
                row_tr.append(td_term)

                # 7. Time
                td_time = template_soup.new_tag("td")
                td_time.string = cls["time"]
                row_tr.append(td_time)

                # 8. Room
                td_room = template_soup.new_tag("td")
                td_room.string = cls["room"]
                row_tr.append(td_room)

                # 9. Lecturer
                td_lec = template_soup.new_tag("td")
                td_lec.string = cls["lecturer"]
                row_tr.append(td_lec)

                # 10. Type
                td_type = template_soup.new_tag("td")
                td_type.string = "Standar/Reg"
                row_tr.append(td_type)

                tbody.append(row_tr)
                row_id_counter += 1

        return str(template_soup)

    def _parse_jadwal(self, soup: BeautifulSoup) -> dict:
        """Parses the schedule (jadwal) HTML to extract course information.

        Args:
            soup: The BeautifulSoup object of the schedule page.

        Returns:
            dict: A dictionary mapping course names to lists of class details
                  (name, time, room, lecturer).
        """
        courses = {}
        # Find headers
        for hdr in soup.find_all("th", class_=("sub", "border2", "pad2")):
            if not isinstance(hdr, Tag) or hdr.parent is None:
                continue

            course_line = hdr.get_text(strip=True)
            class_list = []

            # Find next siblings (rows)
            curr = hdr.parent.find_next_sibling("tr")
            while curr:
                if not isinstance(curr, Tag):
                    curr = curr.find_next_sibling("tr")
                    continue

                # Stop if next course header
                if curr.find("th", class_=("sub", "border2", "pad2")):
                    break

                cells = [td.get_text(strip=True) for td in curr.find_all("td")]
                # Expected format: 0:No, 1:Name, 2:Lang, 3:Period, 4:Time, 5:Room, 6:Lecturer
                if not cells or len(cells) < 7:
                    curr = curr.find_next_sibling("tr")
                    continue

                cls_data = {
                    "name": cells[1],
                    "time": cells[4],
                    "room": cells[5],
                    "lecturer": cells[6],
                }
                class_list.append(cls_data)

                curr = curr.find_next_sibling("tr")

            if class_list:
                courses[course_line] = class_list

        return courses
