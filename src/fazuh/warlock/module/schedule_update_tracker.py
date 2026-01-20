import asyncio
from datetime import datetime
import io
from pathlib import Path
from time import time
from typing import Any

from bs4 import BeautifulSoup
from bs4 import Tag
from loguru import logger
import requests

from fazuh.warlock.config import Config
from fazuh.warlock.siak.siak import Siak


class ScheduleUpdateTracker:
    """Monitors a specific SIAK schedule page for changes.

    Periodically fetches the schedule page, compares it with the previous state,
    and notifies via Discord webhook if any changes (added/removed/modified classes)
    are detected.
    """

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
        self.siak = Siak(self.conf)

    async def start(self):
        """Starts the tracker loop.

        Continuously monitors the schedule at the configured interval.
        """
        if self.conf.is_test:
            await self._run_test()
            return

        try:
            await self.siak.start()

            while True:
                self.conf.load()
                try:
                    if not await self.siak.authenticate():
                        logger.error("Authentication failed.")
                        continue

                    await self.run()
                    logger.success("Schedule update tracker completed successfully.")
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

                logger.info(
                    f"Waiting for the next check in {self.conf.tracker_interval} seconds..."
                )
                await asyncio.sleep(self.conf.tracker_interval)
        finally:
            # Ensure we close browser if loop breaks
            await self.siak.close()

    async def run(self):
        """Executes a single check iteration.

        Fetches the page, parses courses, compares with cache, and sends notifications
        if changes are found.
        """
        # 1. GET tracked page
        if self.siak.page.url != self.conf.tracked_url:
            await self.siak.page.goto(self.conf.tracked_url)

        if not await self.siak.is_logged_in_page():
            logger.error("Not logged in. There was an issue in authenticating.")
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

        logger.debug(f"Changes: {changes}")
        await self._send_changes_to_webhook(self.conf.tracker_discord_webhook_url, changes)

        self.prev_content = curr
        self.cache_file.write_text(curr)

    def _parse_courses_dict(self, content: str) -> dict[str, dict[str, list[str]]]:
        """Parses the raw course content string into a structured dictionary.

        Args:
            content: The raw string content (lines of "Course: | Class1 | Class2").

        Returns:
            dict: Nested dictionary structure for easy comparison.
                  {course_code: {info: str, classes: [str]}}
        """
        result = {}
        for line in content.splitlines():
            if ": |" in line:
                course_info, classes_str = line.split(": |", 1)
                # Extract course code (first part before the dash)
                course_code = course_info.split("-")[0].strip()
                classes = [c.strip() for c in classes_str.split(" | ") if c.strip()]
                result[course_code] = {"info": course_info, "classes": classes}
        return result

    def _generate_detailed_diff(self, old: dict, new: dict) -> list[dict]:
        """Generates a structured diff between old and new course data.

        Identifies new courses, removed courses, and modified courses (added/removed/changed classes).

        Args:
            old: The previous course dictionary.
            new: The current course dictionary.

        Returns:
            list[dict]: A list of change objects suitable for Discord embeds.
        """
        changes = []

        # New courses
        for code in sorted(new.keys() - old.keys()):
            course_info = new[code]["info"]
            course_name = course_info.split(";")[0].strip()

            fields = []
            for class_detail in new[code]["classes"]:
                parts = class_detail.split(";")
                if len(parts) >= 5:
                    kelas = parts[0].replace("Kelas", "").strip()
                    waktu = parts[3].strip().lstrip("- ")
                    ruang = parts[4].strip().lstrip("- ")
                    dosen = parts[5].strip().lstrip("- ") if len(parts) > 5 else "-"
                    fields.append(
                        {
                            "name": kelas,
                            "value": f"- {waktu}\n- {ruang}\n- {dosen}",
                            "inline": False,
                        }
                    )

            changes.append({"type": "new", "title": course_name, "fields": fields})

        # Removed courses
        for code in sorted(old.keys() - new.keys()):
            course_info = old[code]["info"]
            course_name = course_info.split(";")[0].strip()
            changes.append({"type": "removed", "title": course_name, "fields": []})

        # Modified courses
        for code in sorted(old.keys() & new.keys()):
            # Parse classes into dict by class name for easier comparison
            def parse_classes_by_name(classes):
                result = {}
                for class_detail in classes:
                    parts = class_detail.split(";")
                    if len(parts) >= 5:
                        kelas = parts[0].replace("Kelas", "").strip()
                        result[kelas] = {
                            "waktu": parts[3].strip().lstrip("- "),
                            "ruang": parts[4].strip().lstrip("- "),
                            "dosen": parts[5].strip().lstrip("- ") if len(parts) > 5 else "-",
                        }
                return result

            old_classes_dict = parse_classes_by_name(old[code]["classes"])
            new_classes_dict = parse_classes_by_name(new[code]["classes"])

            old_names = set(old_classes_dict.keys())
            new_names = set(new_classes_dict.keys())

            added_names = new_names - old_names
            removed_names = old_names - new_names
            common_names = old_names & new_names

            # Check for modifications within common classes
            modified_names = set()
            for name in common_names:
                if old_classes_dict[name] != new_classes_dict[name]:
                    modified_names.add(name)

            if not added_names and not removed_names and not modified_names:
                continue

            course_info = new[code]["info"]
            course_name = course_info.split(";")[0].strip()

            fields = []

            # Added classes
            for kelas in sorted(added_names):
                info = new_classes_dict[kelas]
                fields.append(
                    {
                        "name": f"[+] ﻿ ﻿ ﻿  {kelas}",
                        "value": f"- {info['waktu']}\n- {info['ruang']}\n- {info['dosen']}",
                        "inline": False,
                    }
                )

            # Modified classes
            for kelas in sorted(modified_names):
                old_info = old_classes_dict[kelas]
                new_info = new_classes_dict[kelas]

                # Show what changed
                lines = []
                if old_info["waktu"] != new_info["waktu"]:
                    lines.append(f"- ~~{old_info['waktu']}~~ → {new_info['waktu']}")

                if old_info["ruang"] != new_info["ruang"]:
                    lines.append(f"- ~~{old_info['ruang']}~~ → {new_info['ruang']}")

                if old_info["dosen"] != new_info["dosen"]:
                    lines.append(f"- ~~{old_info['dosen']}~~ → {new_info['dosen']}")

                fields.append(
                    {"name": f"[Δ] ﻿ ﻿ ﻿ {kelas}", "value": "\n".join(lines), "inline": False}
                )

            # Removed classes
            for kelas in sorted(removed_names):
                info = old_classes_dict[kelas]
                fields.append(
                    {
                        "name": f"[−] ﻿ ﻿ ﻿  {kelas}",
                        "value": f"- ~~{info['waktu']}~~\n- ~~{info['ruang']}~~\n- ~~{info['dosen']}~~",
                        "inline": False,
                    }
                )

            changes.append({"type": "modified", "title": course_name, "fields": fields})

        return changes

    async def _send_changes_to_webhook(self, webhook_url: str, changes: list[dict]):
        """Sends the detected changes to the Discord webhook.

        Uses embeds for small changes and a text file for large changes.

        Args:
            webhook_url: The Discord webhook URL.
            changes: The list of change objects.
        """
        period_code = self._extract_period_from_url(self.conf.tracked_url)
        period_display = self._format_period(period_code)

        base_data: dict[str, Any] = {
            "username": "Warlock Tracker",
            "avatar_url": "https://academic.ui.ac.id/favicon.ico",
        }

        embeds = []
        for change in changes:
            if change["type"] == "new":
                color = 0x57F287  # Green
                title = f"[NEW] ﻿ ﻿ ﻿ {change['title']}"
            elif change["type"] == "removed":
                color = 0xED4245  # Red
                title = f"[REMOVED] ﻿ ﻿ ﻿ {change['title']}"
            else:  # modified
                color = 0xFEE75C  # Yellow
                title = f"[EDITED] ﻿ ﻿ ﻿ {change['title']}"

            embed = {"title": title, "color": color, "fields": change["fields"]}
            embeds.append(embed)

        data = base_data.copy()
        data["content"] = (
            f"## Jadwal SIAK UI Berubah ({period_display})\n﻿\nBetween <t:{int(time() - self.conf.tracker_interval)}:R> to <t:{int(time())}:R>"
        )

        # Discord allows max 10 embeds per webhook
        if len(embeds) > 10:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"siak_schedule_diff_{timestamp}.txt"

            text_content = []
            for change in changes:
                if change["type"] == "new":
                    text_content.append(f"NEW: {change['title']}")
                elif change["type"] == "removed":
                    text_content.append(f"REMOVED: {change['title']}")
                else:
                    text_content.append(f"EDITED: {change['title']}")

                for field in change["fields"]:
                    text_content.append(f"  {field['name']}: {field['value']}")
                text_content.append("")

            diff_file = io.BytesIO("\n".join(text_content).encode("utf-8"))

            data = base_data.copy()
            data["content"] += "﻿\n\n*(Terlalu banyak perubahan, lihat file)*"
            files = {"file": (filename, diff_file, "text/plain")}

            try:
                resp = await asyncio.to_thread(requests.post, webhook_url, data=data, files=files)
                resp.raise_for_status()
                logger.info("Changes sent to webhook as file.")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending to webhook: {e}")
            finally:
                diff_file.close()
            return

        data["embeds"] = embeds

        # Add link button to SIAK
        data["components"] = [
            {
                "type": 1,  # Action Row
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 5,  # Link
                        "label": "Buka SIAK",
                        "url": self.conf.tracked_url,
                    }
                ],
            }
        ]

        try:
            resp = await asyncio.to_thread(requests.post, webhook_url, json=data)
            resp.raise_for_status()
            logger.info("Changes sent to webhook successfully.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending to webhook: {e}")

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

    async def _run_test(self):
        """Simulate changes for all course modification cases and output to terminal."""
        logger.info("Test mode enabled. Simulating schedule updates...")

        # Mock Data
        # 1. New Course: "CS101 - Intro to CS"
        # 2. Removed Course: "OLD999 - Deprecated Course"
        # 3. Modified Course (Class Added): "MATH202 - Linear Algebra"
        # 4. Modified Course (Class Removed): "PHYS101 - Physics I"

        # Helper to create class string matching the format:
        # "Kelas Teori Matriks (A); Indonesia; 25/08/2025 - 19/12/2025; Rabu, 08.00-09.40; D.109; - Dra. ..."
        def mk_cls(name, time, room):
            return f"Kelas {name}; Indonesia; 25/08/2025 - 19/12/2025; {time}; {room}; - Dosen"

        old_courses_list = [
            f"OLD999 - Deprecated Course: | {mk_cls('A', 'Mon 08.00', '101')}",
            f"MATH202 - Linear Algebra: | {mk_cls('A', 'Tue 10.00', '202')}",
            f"PHYS102 - Physics II: | {mk_cls('A', 'Wed 08.00', '303')}",
            f"UNCHANGED01 - Static Course: | {mk_cls('A', 'Fri 13.00', '404')}",
            "SCMA601006 -Aljabar Linier 1(3 SKS, Term 2); Kurikulum 01.01.03.01-2024: | KelasAlin 1 (A); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; Lab. Multidisiplin 303Lab. Multidisiplin 303; - Dr. Hengki Tasman, S.Si., M.Si. | KelasAlin 1 (B); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Jumat, 08.00-09.40; Planet Earth; - Dr. Dipo Aldila, S.Si., M.Si. | KelasAlin 1 (D); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.401B.401; - Dr. Denny Riama Silaban, M.Kom. | KelasAlin 1 (E); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.303B.303; - Dra. Siti Aminah, S.Si., M.Kom. | KelasAlin 1 (F); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; D.403D.403; - Dr. Debi Oktia Haryeni, S.Si., M.Si.-  Satoru Gojo, Ph.D.",
        ]

        new_courses_list = [
            f"CS101 - Intro to CS: | {mk_cls('A', 'Mon 10.00', 'LAB1')}",  # New
            f"MATH202 - Linear Algebra: | {mk_cls('A', 'Tue 10.00', '202')} | {mk_cls('B', 'Thu 10.00', '202')}",  # Class B added
            f"PHYS101 - Physics I: | {mk_cls('A', 'Wed 08.00', '303')}",  # Class B removed
            f"PHYS102 - Physics II: | {mk_cls('A', 'Wed 08.00', '303')} | {mk_cls('B', 'Wed 10.00', '303')} | {mk_cls('C', 'Wed 10.00', '303')}",  # Class B, C added
            f"UNCHANGED01 - Static Course: | {mk_cls('A', 'Fri 13.00', '404')}",
            "SCMA601006 -Aljabar Linier 1(3 SKS, Term 2); Kurikulum 01.01.03.01-2024: | KelasAlin 1 (B); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.402B.402; - Dr. Dipo Aldila, S.Si., M.Si. | KelasAlin 1 (C); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.405B.405; - Dr. Helen Burhan, S.Si., M.Si. | KelasAlin 1 (E); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.303B.303; - Dra. Siti Aminah, S.Si., M.Kom. | KelasAlin 1 (F); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; D.403D.403; - Dr. Debi Oktia Haryeni, S.Si., M.Si.-  Herolistra Baskoroputro, Ph.D.",
        ]

        old_content = "\n".join(old_courses_list)
        new_content = "\n".join(new_courses_list)

        old_courses = self._parse_courses_dict(old_content)
        new_courses = self._parse_courses_dict(new_content)

        changes = self._generate_detailed_diff(old_courses, new_courses)

        if changes:
            logger.info(f"Simulation finished. Sending {len(changes)} changes to webhook...")
            await self._send_changes_to_webhook(self.conf.tracker_discord_webhook_url, changes)
        else:
            logger.warning("No changes detected (unexpected for this test).")
