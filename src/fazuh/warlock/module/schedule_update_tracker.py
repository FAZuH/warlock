import asyncio
from datetime import datetime
import difflib
import io
from pathlib import Path

from bs4 import BeautifulSoup
from bs4 import Tag
from loguru import logger
import requests

from fazuh.warlock.config import Config
from fazuh.warlock.siak.siak import Siak


class ScheduleUpdateTracker:
    def __init__(self):
        self.conf = Config()

        data_folder = Path("data")
        if not data_folder.exists():
            data_folder.mkdir(parents=True)

        self.cache_file = data_folder.joinpath("latest_courses.txt")
        self._first_run_no_cache = not self.cache_file.exists()
        if self._first_run_no_cache:
            self.cache_file.touch()

        self.prev_content = self.cache_file.read_text() if self.cache_file.exists() else ""

    async def start(self):
        self.siak = Siak(self.conf)
        await self.siak.start()
        while True:
            self.conf.load()  # Reload config to allow dynamic changes to .env
            try:
                await self.siak.authenticate()
                await self.run()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                await self.siak.close()
            else:
                logger.info("Schedule update tracker completed successfully.")
            finally:
                logger.info(
                    f"Waiting for the next check in {self.conf.tracker_interval} seconds..."
                )
                await asyncio.sleep(self.conf.tracker_interval)

    async def run(self):
        # 1. GET tracked page
        await self.siak.page.goto(self.conf.tracked_url)
        if self.siak.page.url != self.conf.tracked_url:
            logger.error(f"Expected {self.conf.tracked_url}. Found {self.siak.page.url} instead.")
            return
        if await self.siak.is_captcha_page():
            logger.error("Captcha page detected. Please solve the captcha manually.")
            return
        if not await self.siak.is_logged_in():
            logger.error("Not logged in. Please check your credentials.")
            return

        # 2. Parse response
        content = await self.siak.page.content()
        soup = BeautifulSoup(content, "html.parser")

        courses: list[str] = []

        # every course starts with <th class="sub ...">
        for hdr in soup.find_all("th", class_=("sub", "border2", "pad2")):
            if hdr.parent is None:
                continue
            # 2a. course header
            course_line = hdr.get_text(strip=True)
            course_line = course_line.replace("<strong>", "").replace("</strong>", "")

            # 2b. collect all following <tr> rows that belong to this course
            classes_info = []
            for sibling in hdr.parent.find_next_siblings("tr"):
                if not isinstance(sibling, Tag):
                    continue

                # stop if we hit the next course header
                if sibling.find("th", class_=("sub", "border2", "pad2")):
                    break

                # collect the text of every <td> in this <tr>
                cells = [td.get_text(strip=True) for td in sibling.find_all("td")]
                if not cells:
                    continue

                # build one line per class, e.g.
                # "Kelas Teori Matriks (A); Indonesia; 25/08/2025 - 19/12/2025; Rabu, 08.00-09.40; D.109; - Dra. ..."
                class_line = "; ".join(cells[1:])  # skip the first cell (index number)
                classes_info.append(class_line)

            # 2c. merge course header + its classes
            full_entry = (
                f"{course_line}: | " + " | ".join(classes_info) if classes_info else course_line
            )
            courses.append(full_entry)

        curr = "\n".join(courses)

        # 3. Compare with previous content
        if self.prev_content == curr:
            logger.info("No updates detected.")
            return

        if self._first_run_no_cache:
            logger.info(
                "First run with no previous cache. Saving initial state without notification."
            )
            self.prev_content = curr
            self.cache_file.write_text(curr)
            self._first_run_no_cache = False
            return

        logger.info("Update detected!")

        # Parse old and new into structured format for better diff
        old_courses = self._parse_courses_dict(self.prev_content)
        new_courses = self._parse_courses_dict(curr)

        changes = self._generate_detailed_diff(old_courses, new_courses)
        
        if not changes:
            logger.info("No meaningful changes detected (only order changed).")
            return

        logger.debug("\n".join(changes))
        await self._send_changes_to_webhook(self.conf.tracker_discord_webhook_url, changes)

        self.prev_content = curr
        self.cache_file.write_text(curr)

    def _parse_courses_dict(self, content: str) -> dict[str, dict[str, list[str]]]:
        """Parse course content into nested dict: {course_code: {course_info: str, classes: [class_details]}"""
        result = {}
        for line in content.splitlines():
            if ": |" in line:
                course_info, classes_str = line.split(": |", 1)
                # Extract course code (first part before the dash)
                course_code = course_info.split("-")[0].strip()
                classes = [c.strip() for c in classes_str.split(" | ") if c.strip()]
                result[course_code] = {
                    "info": course_info,
                    "classes": classes
                }
        return result

    def _generate_detailed_diff(self, old: dict, new: dict) -> list[str]:
        """Generate human-readable diff showing what changed."""
        changes = []
        
        # New courses
        for code in sorted(new.keys() - old.keys()):
            course_info = new[code]["info"]
            course_name = course_info.split(";")[0].strip()
            changes.append(f"- **🆕 {course_name}**")
            for class_detail in new[code]["classes"]:
                parts = class_detail.split(";")
                if len(parts) >= 5:
                    kelas = parts[0].replace("Kelas", "").strip()
                    waktu = parts[3].strip()
                    ruang = parts[4].strip()
                    changes.append(f"  - {kelas}: `{waktu}` di `{ruang}`")
            changes.append("")
        
        # Removed courses
        for code in sorted(old.keys() - new.keys()):
            course_info = old[code]["info"]
            course_name = course_info.split(";")[0].strip()
            changes.append(f"- **🗑️ {course_name}**")
            changes.append("")
        
        # Modified courses
        for code in sorted(old.keys() & new.keys()):
            old_classes = set(old[code]["classes"])
            new_classes = set(new[code]["classes"])
            
            added = new_classes - old_classes
            removed = old_classes - new_classes
            
            if not added and not removed:
                continue
            
            course_info = new[code]["info"]
            course_name = course_info.split(";")[0].strip()
            changes.append(f"- **✏️ {course_name}**")
            
            for class_detail in removed:
                parts = class_detail.split(";")
                if len(parts) >= 5:
                    kelas = parts[0].replace("Kelas", "").strip()
                    waktu = parts[3].strip()
                    ruang = parts[4].strip()
                    changes.append(f"  - ❌ ~~{kelas}: `{waktu}` di `{ruang}`~~")
            
            for class_detail in added:
                parts = class_detail.split(";")
                if len(parts) >= 5:
                    kelas = parts[0].replace("Kelas", "").strip()
                    waktu = parts[3].strip()
                    ruang = parts[4].strip()
                    changes.append(f"  - ✅ {kelas}: `{waktu}` di `{ruang}`")
            
            changes.append("")
        
        return changes

    async def _send_changes_to_webhook(self, webhook_url: str, changes: list[str]):
        """Send changes to Discord, splitting into multiple messages if needed."""
        # Extract period from tracked_url
        period_code = self._extract_period_from_url(self.conf.tracked_url)
        period_display = self._format_period(period_code)
        
        message_header = f"## Jadwal SIAK UI Berubah ({period_display})\n"
        base_data = {
            "username": "Warlock Tracker",
            "avatar_url": "https://academic.ui.ac.id/favicon.ico",
        }
        
        MAX_LENGTH = 1900
        
        full_message = message_header + "\n".join(changes)
        
        if len(full_message) < MAX_LENGTH:
            data = base_data.copy()
            data["content"] = full_message
            try:
                resp = await asyncio.to_thread(requests.post, webhook_url, json=data)
                resp.raise_for_status()
                logger.info("Changes sent to webhook successfully.")
                return
            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending to webhook: {e}")
                return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"siak_schedule_diff_{timestamp}.txt"
        diff_content = "\n".join(changes)
        diff_file = io.BytesIO(diff_content.encode("utf-8"))
        
        data = base_data.copy()
        data["content"] = f"{message_header}\n*(Perubahan terlalu panjang, lihat file)*"
        files = {"file": (filename, diff_file, "text/plain")}
        
        try:
            resp = await asyncio.to_thread(requests.post, webhook_url, data=data, files=files)
            resp.raise_for_status()
            logger.info("Changes sent to webhook as file successfully.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending to webhook: {e}")
        finally:
            diff_file.close()

    def _extract_period_from_url(self, url: str) -> str:
        """Extract period code from URL. Returns '2025-2' from '...?period=2025-2'"""
        if "period=" in url:
            return url.split("period=")[1].split("&")[0]
        return "Unknown"

    def _format_period(self, period_code: str) -> str:
        """Convert period code to readable format. '2025-2' -> 'Semester Genap 2025/2026'"""
        if "-" not in period_code:
            return period_code
        
        year, semester = period_code.split("-")
        semester_name = "Ganjil" if semester == "1" else "Genap"
        next_year = str(int(year) + 1)
        
        return f"Semester {semester_name} {year}/{next_year}"
