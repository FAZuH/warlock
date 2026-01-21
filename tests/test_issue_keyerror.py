import pytest
from unittest.mock import MagicMock, patch
from fazuh.warlock.module.schedule_update_tracker import ScheduleUpdateTracker


@pytest.mark.asyncio
async def test_webhook_large_payload_chunking():
    """
    Test that _send_changes_to_webhook correctly chunks > 10 changes
    and creates a thread.
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

        # Create 15 changes to trigger chunking (10 + 5)
        changes = []
        for i in range(15):
            changes.append(
                {
                    "type": "new",
                    "title": f"Course {i}",
                    "fields": [{"name": "Class A", "value": "Details", "inline": False}],
                }
            )

        # Mock requests.post
        with patch("requests.post") as mock_post:
            # Setup response for the first call (thread creation)
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "123456789"}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            await tracker._send_changes_to_webhook("http://fake.url", changes)

            # Verify calls
            assert mock_post.call_count == 2

            # First call: Create thread
            args1, kwargs1 = mock_post.call_args_list[0]
            assert kwargs1["params"] == {"wait": "true"}
            assert "thread_name" in kwargs1["json"]
            assert len(kwargs1["json"]["embeds"]) == 10

            # Second call: Post to thread
            args2, kwargs2 = mock_post.call_args_list[1]
            assert kwargs2["params"] == {"thread_id": "123456789"}
            assert len(kwargs2["json"]["embeds"]) == 5
