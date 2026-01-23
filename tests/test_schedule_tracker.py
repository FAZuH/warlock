from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from fazuh.warlock.module.schedule.cache import ScheduleCache
from fazuh.warlock.module.track import Track
from fazuh.warlock.siak.siak import Siak


@pytest.fixture
def mock_siak():
    siak = MagicMock(spec=Siak)
    siak.page = MagicMock()
    siak.page.goto = AsyncMock()
    siak.page.url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanView"
    siak.is_captcha_page = AsyncMock(return_value=False)
    siak.is_logged_in = AsyncMock(return_value=True)
    siak.is_logged_in_page = AsyncMock(return_value=True)
    return siak


@pytest_asyncio.fixture
async def schedule_html():
    path = Path(__file__).parent / "mock" / "schedule_page.html"
    return path.read_text(encoding="windows-1252")


@pytest.mark.asyncio
async def test_schedule_tracker_run(mock_siak, schedule_html, tmp_path):
    # Setup mock page content
    mock_siak.page.content = AsyncMock(return_value=schedule_html)

    # Mock Config to avoid loading real .env
    with patch("fazuh.warlock.module.track.Config") as mock_config_cls:
        mock_conf = mock_config_cls.return_value
        mock_conf.tracked_url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanView"
        mock_conf.tracker_discord_webhook_url = "http://mock-webhook"
        mock_conf.tracker_interval = 60
        mock_conf.tracker_suppress_professor_change = False
        mock_conf.tracker_suppress_location_change = False

        # Patch ScheduleCache to use tmp_path
        cache_file_path = tmp_path / "latest_courses.txt"

        def mock_cache_init(*args, **kwargs):
            return ScheduleCache(file_path=cache_file_path)

        with patch(
            "fazuh.warlock.module.track.ScheduleCache",
            side_effect=mock_cache_init,
        ):
            # Mock send_notifications
            with patch(
                "fazuh.warlock.module.track.send_notifications",
                new_callable=AsyncMock,
            ) as mock_send:
                tracker = Track()
                tracker.siak = mock_siak

                # First run - should save cache and NOT notify
                await tracker.run()
                assert mock_send.call_count == 0

                # Modify cache to simulate a change
                original_content = cache_file_path.read_text()

                # Remove one line from cache to simulate it being "added" in the next run
                lines = original_content.splitlines()
                # We need to be careful what we remove. The cache format is "Course: | Class"
                # Let's remove the first course entry
                lines.pop(0)
                cache_file_path.write_text("\n".join(lines))

                # Re-init tracker to load modified cache
                tracker = Track()
                tracker.siak = mock_siak
                tracker.conf = mock_conf  # Ensure config is set

                # Second run - should detect update and notify
                await tracker.run()

                assert mock_send.called
                args = mock_send.call_args[0]
                assert args[0] == "http://mock-webhook"
                changes = args[1]
                # Verify that some change was detected (should show the added course)
                assert any(change["type"] == "new" for change in changes)
