import time
from typing import List

import aiohttp
import discord
from loguru import logger

from fazuh.warlock.module.schedule.diff import Change


def _extract_period_from_url(url: str) -> str:
    """Extract period code from URL. Returns '2025-2' from '...?period=2025-2'"""
    if "period=" in url:
        return url.split("period=")[1].split("&")[0]
    return "Unknown"


def _format_period(period_code: str) -> str:
    """Convert period code to readable format. '2025-2' -> 'Semester Genap 2025/2026'"""
    if "-" not in period_code:
        return period_code

    year, semester = period_code.split("-")
    semester_name = "Ganjil" if semester == "1" else "Genap"
    next_year = str(int(year) + 1)

    return f"Semester {semester_name} {year}/{next_year}"


async def send_notifications(
    webhook_url: str, changes: List[Change], tracked_url: str, interval: int
):
    """
    Sends the detected changes to the Discord webhook.

    Uses embeds for small changes and a text file for large changes.

    Args:
        webhook_url: The Discord webhook URL.
        changes: The list of change objects.
        tracked_url: The URL being tracked (for period extraction).
        interval: The check interval (for timestamp).
    """
    period_code = _extract_period_from_url(tracked_url)
    period_display = _format_period(period_code)

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
        f"Between <t:{int(time.time() - interval)}:R> to <t:{int(time.time())}:R>"
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
