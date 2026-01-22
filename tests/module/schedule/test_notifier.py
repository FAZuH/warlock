from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from fazuh.warlock.module.schedule.notifier import _extract_period_from_url
from fazuh.warlock.module.schedule.notifier import _format_period
from fazuh.warlock.module.schedule.notifier import send_notifications


def test_extract_period_from_url():
    url = "https://academic.ui.ac.id/main/Schedule/Index?period=2025-2&search="
    assert _extract_period_from_url(url) == "2025-2"

    url = "https://academic.ui.ac.id/main/Schedule/Index"
    assert _extract_period_from_url(url) == "Unknown"


def test_format_period():
    assert _format_period("2025-2") == "Semester Genap 2025/2026"
    assert _format_period("2025-1") == "Semester Ganjil 2025/2026"
    assert _format_period("Unknown") == "Unknown"


@pytest.mark.asyncio
async def test_send_notifications():
    changes = [
        {
            "type": "new",
            "title": "CS101",
            "fields": [{"name": "A", "value": "Info", "inline": False}],
        }
    ]

    with patch("aiohttp.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        with patch("discord.Webhook.from_url") as mock_webhook_cls:
            mock_webhook = AsyncMock()
            mock_webhook_cls.return_value = mock_webhook

            await send_notifications(
                webhook_url="http://webhook",
                changes=changes,
                tracked_url="http://url?period=2025-2",
                interval=60,
            )

            mock_webhook.send.assert_called()
            call_kwargs = mock_webhook.send.call_args.kwargs
            assert len(call_kwargs["embeds"]) == 1
            assert "Jadwal SIAK UI Berubah" in call_kwargs["content"]
