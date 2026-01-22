from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from fazuh.warlock.module.schedule.notifier import send_notifications


@pytest.mark.asyncio
async def test_webhook_large_payload_chunking():
    """
    Test that send_notifications correctly chunks > 10 changes.
    """
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

        # We need to mock aiohttp.ClientSession as well since send_notifications uses it
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session.return_value.__aenter__.return_value = AsyncMock()

            await send_notifications(
                webhook_url="http://fake.url",
                changes=changes,
                tracked_url="http://siak.ui.ac.id/schedule?period=2025-2",
                interval=60,
            )

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
