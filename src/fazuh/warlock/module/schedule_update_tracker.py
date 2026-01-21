import asyncio
from pathlib import Path
from time import time

import aiohttp
from bs4 import BeautifulSoup
from bs4 import Tag
import discord
from loguru import logger

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
        self.conf.load()

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

            embed = discord.Embed(title=title, color=color)
            for field in change["fields"]:
                embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
            embeds.append(embed)

        content = (
            f"## Jadwal SIAK UI Berubah ({period_display})\n\n"
            f"Between <t:{int(time() - self.conf.tracker_interval)}:R> to <t:{int(time())}:R>"
        )

        # Chunk embeds (Discord allows max 10 embeds per webhook)
        chunks = [embeds[i : i + 10] for i in range(0, len(embeds), 10)]

        if not chunks:
            logger.warning("No embeds to send.")
            return

        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)

            try:
                for i, chunk in enumerate(chunks):
                    kwargs = {
                        "embeds": chunk,
                        "username": "Warlock Tracker",
                        "avatar_url": "https://academic.ui.ac.id/favicon.ico",
                        "wait": True,
                    }

                    # Only include content (header) in the first message
                    if i == 0:
                        kwargs["content"] = content

                    logger.debug(f"Sending chunk {i + 1}/{len(chunks)} with {len(chunk)} embeds.")
                    await webhook.send(**kwargs)
                    logger.info(f"Sent chunk {i + 1}/{len(chunks)} to webhook.")

                logger.info("Changes sent to webhook successfully.")

            except discord.HTTPException as e:
                logger.error(f"Error sending to webhook: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")

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
