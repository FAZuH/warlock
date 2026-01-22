from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio

from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker
from fazuh.warlock.siak.siak import Siak


@pytest.fixture
def mock_siak():
    siak = MagicMock(spec=Siak)
    siak.page = MagicMock()
    siak.page.goto = AsyncMock()
    siak.page.url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanView"
    siak.is_captcha_page = AsyncMock(return_value=False)
    siak.is_logged_in = AsyncMock(return_value=True)
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
    with patch("fazuh.warlock.module.schedule_update_tracker.Config") as mock_config_cls:
        mock_conf = mock_config_cls.return_value
        mock_conf.tracked_url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanView"
        mock_conf.tracker_discord_webhook_url = "http://mock-webhook"

        # Patch data folder to use tmp_path
        with patch("fazuh.warlock.module.schedule_update_tracker.Path") as mock_path_cls:
            # We want Path("data") to return a mock that points to tmp_path
            mock_data_dir = tmp_path / "data"
            mock_data_dir.mkdir()

            def mock_path_init(path_str):
                if path_str == "data":
                    return mock_data_dir
                return Path(path_str)

            mock_path_cls.side_effect = mock_path_init

            tracker = ScheduleUpdateTracker()
            tracker.siak = mock_siak

            # Mock the webhook send to avoid network calls
            tracker._send_changes_to_webhook = AsyncMock()

            # First run - should save cache and NOT notify
            await tracker.run()
            assert tracker._send_changes_to_webhook.call_count == 0

            # Modify cache to simulate a change
            cache_file = mock_data_dir / "latest_courses.txt"
            original_content = cache_file.read_text()

            # Remove one line from cache to simulate it being "added" in the next run
            lines = original_content.splitlines()
            lines.pop(0)
            cache_file.write_text("\n".join(lines))

            # Re-init tracker to load modified cache
            tracker = ScheduleUpdateTracker()
            tracker.siak = mock_siak
            tracker._send_changes_to_webhook = AsyncMock()
            tracker.conf.tracked_url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanView"

            # Second run - should detect update and notify
            await tracker.run()

            assert tracker._send_changes_to_webhook.called
            args = tracker._send_changes_to_webhook.call_args[0]
            assert args[0] == "http://mock-webhook"
            changes = args[1]
            # Verify that some change was detected (should show the added course)
            assert any(change["type"] == "new" for change in changes)


from unittest.mock import patch

import pytest

from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker


@pytest.fixture
def tracker():
    with (
        patch("fazuh.warlock.module.schedule_update_tracker.Config") as MockConfig,
        patch("fazuh.warlock.module.schedule_update_tracker.Path") as MockPath,
        patch("fazuh.warlock.module.schedule_update_tracker.Siak"),
    ):
        # Setup mock config instance
        mock_conf_instance = MockConfig.return_value
        mock_conf_instance.tracker_suppress_professor_change = False
        mock_conf_instance.tracker_suppress_location_change = False

        # Setup mock path to avoid file system errors
        MockPath.return_value.exists.return_value = True
        MockPath.return_value.read_text.return_value = ""

        tracker = ScheduleUpdateTracker()
        # Ensure the conf used is our mock
        tracker.conf = mock_conf_instance
        return tracker


def test_suppress_professor_change(tracker):
    tracker.conf.tracker_suppress_professor_change = True

    old_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. Old"],
        }
    }

    new_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. New"],
        }
    }

    changes = tracker._generate_detailed_diff(old_data, new_data)
    assert len(changes) == 0


def test_suppress_location_change(tracker):
    tracker.conf.tracker_suppress_location_change = True

    old_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. X"],
        }
    }

    new_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 102; Prof. X"],
        }
    }

    changes = tracker._generate_detailed_diff(old_data, new_data)
    assert len(changes) == 0


def test_no_suppress_if_time_changed(tracker):
    tracker.conf.tracker_suppress_professor_change = True
    tracker.conf.tracker_suppress_location_change = True

    old_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. X"],
        }
    }

    new_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 10.00-12.00; Room 101; Prof. X"],
        }
    }

    changes = tracker._generate_detailed_diff(old_data, new_data)
    assert len(changes) == 1
    assert changes[0]["type"] == "modified"


def test_no_suppress_if_multiple_changes(tracker):
    # If both professor and location change, we should probably notify even if both suppressions are on?
    # The requirement says "professor ONLY change" and "class location ONLY change".
    # So if both change, it's not "only" one of them.

    tracker.conf.tracker_suppress_professor_change = True
    tracker.conf.tracker_suppress_location_change = True

    old_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. Old"],
        }
    }

    new_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 102; Prof. New"],
        }
    }

    changes = tracker._generate_detailed_diff(old_data, new_data)
    assert len(changes) == 1
    assert changes[0]["type"] == "modified"


def test_default_behavior_no_suppression(tracker):
    # Default behavior (False) should report all changes
    tracker.conf.tracker_suppress_professor_change = False
    tracker.conf.tracker_suppress_location_change = False

    old_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. Old"],
        }
    }

    new_data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; ; ; Senin, 08.00-10.00; Room 101; Prof. New"],
        }
    }

    changes = tracker._generate_detailed_diff(old_data, new_data)
    assert len(changes) == 1
    assert changes[0]["type"] == "modified"
