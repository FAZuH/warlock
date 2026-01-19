import asyncio
from datetime import datetime
import difflib
import io
from pathlib import Path

from bs4 import BeautifulSoup
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
        if not self.cache_file.exists():
            self.cache_file.touch()

        self.prev_content = self.cache_file.read_text() if self.cache_file.exists() else ""

    async def start(self):
        self.siak = Siak(self.conf.username, self.conf.password)
        await self.siak.start()
        await self.siak.authenticate()
        while True:
            self.conf.load()  # Reload config to allow dynamic changes to .env
            try:
                # Try to use existing session
                if not self.siak.is_logged_in(await self.siak.content):
                    # Otherwise re-authenticate
                    await self.siak.close()
                    self.siak = Siak(self.conf.username, self.conf.password)
                    await self.siak.start()
                    if not await self.siak.authenticate():
                        continue

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
        if not self.siak.is_captcha_page(await self.siak.content):
            logger.error("Captcha page detected. Please solve the captcha manually.")
            return
        if not self.siak.is_logged_in(await self.siak.content):
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
        logger.info("Update detected!")

        # compare using set
        old_courses = set(self.prev_content.splitlines()) if self.prev_content else set()
        new_courses = set(courses)
        added_courses = new_courses - old_courses
        removed_courses = old_courses - new_courses

        changes = []
        changes.extend([f"+ {e}" for e in added_courses])
        changes.extend([f"- {e}" for e in removed_courses])
        changes.sort()
        if not changes:
            logger.info("No meaningful changes detected (only order changed).")
            return

        # 4. Create diff and send to webhook
        diff = "\n".join(changes)
        logger.debug(diff)
        await self._send_diff_to_webhook(self.conf.tracker_discord_webhook_url, diff)

        self.prev_content = curr
        self.cache_file.write_text(curr)

    async def _send_diff_to_webhook(self, webhook_url: str, diff: str):
        message = "**Jadwal SIAK UI Berubah!**"
        data = {
            "username": "Warlock Tracker",
            "avatar_url": "https://academic.ui.ac.id/favicon.ico",
        }
        files = None
        diff_file = None

        # Discord has a 2000 character limit for messages (see https://discord.com/developers/docs/resources/webhook#execute-webhook-jsonform-params)
        # Send text if diff is under 1900 characters, otherwise send as file
        if len(diff) < 1900:
            data["content"] = f"{message}\n```diff\n{diff}\n```"
        else:
            data["content"] = message
            diff_file = io.BytesIO(diff.encode("utf-8"))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"siak_schedule_diff_{timestamp}.txt"
            files = {"file": (filename, diff_file, "text/plain")}

        try:
            resp = await asyncio.to_thread(requests.post, webhook_url, data=data, files=files)
            resp.raise_for_status()
            logger.info("Content sent to webhook successfully.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending content to webhook: {e}")
        finally:
            if diff_file:
                diff_file.close()

    def _get_diff(self, old: str, new: str) -> str:
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
        return "".join(diff)
