from loguru import logger
import pytest

from fazuh.warlock.module.schedule.diff import generate_diff
from fazuh.warlock.module.schedule.notifier import send_notifications
from fazuh.warlock.module.schedule.parser import parse_schedule_string
from fazuh.warlock.module.track import Track


@pytest.mark.webhook
@pytest.mark.asyncio
async def test_tracker_simulation():
    """Simulate changes for all course modification cases and output to terminal."""
    tracker = Track()
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
        "SCMA601006 -Aljabar Linier 1(3 SKS, Term 2); Kurikulum 01.01.03.01-2024: | KelasAlin 1 (A); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; Lab. Multidisiplin 303Lab. Multidisiplin 303; - Dr. Fake Name 1, S.Si., M.Si. | KelasAlin 1 (B); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Jumat, 08.00-09.40; Planet Earth; - Dr. Fake Name 2, S.Si., M.Si. | KelasAlin 1 (D); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.401B.401; - Dr. Fake Name 3, M.Kom. | KelasAlin 1 (E); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.303B.303; - Dra. Fake Name 4, S.Si., M.Kom. | KelasAlin 1 (F); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; D.403D.403; - Dr. Fake Name 5, S.Si., M.Si.-  Dr. Anime Character, Ph.D.",
    ]

    new_courses_list = [
        f"CS101 - Intro to CS: | {mk_cls('A', 'Mon 10.00', 'LAB1')}",  # New
        f"MATH202 - Linear Algebra: | {mk_cls('A', 'Tue 10.00', '202')} | {mk_cls('B', 'Thu 10.00', '202')}",  # Class B added
        f"PHYS101 - Physics I: | {mk_cls('A', 'Wed 08.00', '303')}",  # Class B removed
        f"PHYS102 - Physics II: | {mk_cls('A', 'Wed 08.00', '303')} | {mk_cls('B', 'Wed 10.00', '303')} | {mk_cls('C', 'Wed 10.00', '303')}",  # Class B, C added
        f"UNCHANGED01 - Static Course: | {mk_cls('A', 'Fri 13.00', '404')}",
        "SCMA601006 -Aljabar Linier 1(3 SKS, Term 2); Kurikulum 01.01.03.01-2024: | KelasAlin 1 (B); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.402B.402; - Dr. Fake Name 2, S.Si., M.Si. | KelasAlin 1 (C); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.405B.405; - Dr. Fake Name 6, S.Si., M.Si. | KelasAlin 1 (E); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; B.303B.303; - Dra. Fake Name 4, S.Si., M.Kom. | KelasAlin 1 (F); Indonesia; 02/02/2026 - 05/06/202602/02/2026 - 05/06/2026; Senin, 13.00-14.40Kamis, 08.00-09.40; D.403D.403; - Dr. Fake Name 5, S.Si., M.Si.-  Dr. Fake Name 7, Ph.D.",
    ]

    old_content = "\n".join(old_courses_list)
    new_content = "\n".join(new_courses_list)

    old_courses = parse_schedule_string(old_content)
    new_courses = parse_schedule_string(new_content)

    changes = generate_diff(old_courses, new_courses)

    if changes:
        logger.info(f"Simulation finished. Sending {len(changes)} changes to webhook...")
        await send_notifications(
            tracker.conf.tracker_discord_webhook_url,
            changes,
            tracker.conf.tracked_url,
            tracker.conf.tracker_interval,
        )
    else:
        logger.warning("No changes detected (unexpected for this test).")
        assert False, "No changes detected (unexpected for this test)."
