from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

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

        # Mock discord.Webhook.from_url
        with patch("discord.Webhook.from_url") as mock_from_url:
            mock_webhook = MagicMock()
            mock_from_url.return_value = mock_webhook

            # Mock send method
            mock_send = AsyncMock()
            mock_webhook.send = mock_send

            # Setup return value for the first call (thread creation)
            mock_message = MagicMock()
            mock_message.id = 123456789
            mock_send.return_value = mock_message

            await tracker._send_changes_to_webhook("http://fake.url", changes)

            # Verify calls
            assert mock_send.call_count == 2

            # First call: First chunk with content
            args1, kwargs1 = mock_send.call_args_list[0]
            assert kwargs1["wait"] is True
            assert "content" in kwargs1
            assert len(kwargs1["embeds"]) == 10
            assert "thread_name" not in kwargs1

            # Second call: Second chunk without content
            args2, kwargs2 = mock_send.call_args_list[1]
            assert kwargs2["wait"] is True
            assert "content" not in kwargs2
            assert len(kwargs2["embeds"]) == 5
            assert "thread" not in kwargs2
