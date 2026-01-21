import pytest
from unittest.mock import MagicMock, patch
from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker


@pytest.mark.asyncio
async def test_webhook_large_payload_keyerror_fix():
    """
    Test that _send_changes_to_webhook correctly handles > 10 changes
    without raising KeyError: 'content' when falling back to file upload.
    """
    # Mock dependencies
    with (
        patch("fazuh.warlock.module.schedule_update_tracker.Config") as MockConfig,
        patch("fazuh.warlock.module.schedule_update_tracker.Siak") as MockSiak,
        patch("fazuh.warlock.module.schedule_update_tracker.Path") as MockPath,
    ):
        # Setup mocks
        mock_conf = MockConfig.return_value
        mock_conf.tracker_interval = 60
        mock_conf.tracker_discord_webhook_url = "http://fake.url"
        mock_conf.tracked_url = "http://siak.ui.ac.id/schedule?period=2025-2"

        # Mock Path behavior
        mock_path_instance = MockPath.return_value
        mock_path_instance.exists.return_value = True
        mock_path_instance.joinpath.return_value.exists.return_value = True
        mock_path_instance.joinpath.return_value.read_text.return_value = ""

        tracker = ScheduleUpdateTracker()

        # Create > 10 changes to trigger the file upload logic
        changes = []
        for i in range(15):
            changes.append(
                {
                    "type": "new",
                    "title": f"Course {i}",
                    "fields": [{"name": "Class A", "value": "Details", "inline": False}],
                }
            )

        # We need to mock requests.post to avoid actual network call
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()

            # This should NOT raise KeyError
            try:
                await tracker._send_changes_to_webhook("http://fake.url", changes)
            except KeyError as e:
                pytest.fail(f"Raised KeyError: {e}")

            # Verify that it called post (we don't strictly care about arguments, just that it didn't crash)
            assert mock_post.called
