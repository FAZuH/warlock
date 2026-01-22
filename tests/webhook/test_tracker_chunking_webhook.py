from loguru import logger
import pytest

from fazuh.warlock.module.schedule.diff import generate_diff
from fazuh.warlock.module.schedule.notifier import send_notifications
from fazuh.warlock.module.schedule.parser import parse_schedule_string
from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker


@pytest.mark.webhook
@pytest.mark.asyncio
async def test_tracker_chunking_simulation():
    """Simulate massive changes to trigger chunking logic (more than 10 embeds)."""
    tracker = ScheduleUpdateTracker()
    logger.info("Test mode enabled. Simulating massive schedule updates...")

    # Helper to create class string
    def mk_cls(name, time, room):
        return f"Kelas {name}; Indonesia; 25/08/2025 - 19/12/2025; {time}; {room}; - Dosen"

    old_courses_list = []
    new_courses_list = []

    # Generate 15 new courses to ensure > 10 embeds (since new courses = 1 embed each)
    for i in range(1, 16):
        new_courses_list.append(f"NEW{i:03d} - New Course {i}: | {mk_cls('A', 'Mon 08.00', '101')}")

    old_content = "\n".join(old_courses_list)
    new_content = "\n".join(new_courses_list)

    old_courses = parse_schedule_string(old_content)
    new_courses = parse_schedule_string(new_content)

    changes = generate_diff(old_courses, new_courses)

    if changes:
        logger.info(
            f"Simulation finished. Sending {len(changes)} changes to webhook (should be > 10)..."
        )
        if len(changes) <= 10:
            logger.warning(
                f"Warning: Only {len(changes)} changes generated. Chunking might not be fully tested."
            )

        await send_notifications(
            tracker.conf.tracker_discord_webhook_url,
            changes,
            tracker.conf.tracked_url,
            tracker.conf.tracker_interval,
        )
    else:
        logger.warning("No changes detected (unexpected for this test).")
        assert False, "No changes detected (unexpected for this test)."
