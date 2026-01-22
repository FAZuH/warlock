import asyncio
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import PropertyMock

import discord
import pytest

from fazuh.warlock.bot import CaptchaBot


@pytest.mark.asyncio
async def test_on_message_direct_reply():
    with patch("discord.Client.user", new_callable=PropertyMock) as mock_user:
        bot = CaptchaBot(channel_id=123)
        mock_user_obj = MagicMock()
        mock_user_obj.id = 999
        mock_user.return_value = mock_user_obj

        future = asyncio.Future()
        bot.pending_captchas[555] = future

        message = AsyncMock(spec=discord.Message)
        message.author.id = 111
        message.author.bot = False
        message.content = "123456"
        message.reference.message_id = 555

        # Fix: Explicitly set fetch_message as an AsyncMock to avoid "AsyncMock can't be used in await" error
        bot_message_mock = AsyncMock()
        message.channel.fetch_message = AsyncMock(return_value=bot_message_mock)

        await bot.on_message(message)

        assert future.done()
        assert future.result() == "123456"


@pytest.mark.asyncio
async def test_on_message_fallback_history_check():
    with patch("discord.Client.user", new_callable=PropertyMock) as mock_user:
        bot = CaptchaBot(channel_id=123)
        mock_user_obj = MagicMock()
        mock_user_obj.id = 999
        mock_user.return_value = mock_user_obj

        future = asyncio.Future()
        bot.pending_captchas[555] = future
        bot.latest_captcha_message_id = 555

        # Mock message (NOT a reply, but valid fallback)
        message = AsyncMock(spec=discord.Message)
        message.author.id = 111
        message.author.bot = False
        message.content = "ABCDEF"
        message.channel.id = 123
        message.reference = None

        # Fix: Explicitly set fetch_message as an AsyncMock
        bot_message_mock = AsyncMock()
        message.channel.fetch_message = AsyncMock(return_value=bot_message_mock)

        # Mock history
        # history() returns an async iterator
        # We need to mock the async iterator behavior

        # Create mock messages for history
        prev_msg = AsyncMock(spec=discord.Message)
        prev_msg.id = 555  # Matches latest captcha

        # Mock the history method to return an async iterator
        async def mock_history_gen(*args, **kwargs):
            yield message  # Current message
            yield prev_msg  # Previous message (captcha)

        message.channel.history = mock_history_gen

        await bot.on_message(message)

        assert future.done()
        assert future.result() == "ABCDEF"


@pytest.mark.asyncio
async def test_on_message_fallback_history_fail():
    with patch("discord.Client.user", new_callable=PropertyMock) as mock_user:
        bot = CaptchaBot(channel_id=123)
        mock_user_obj = MagicMock()
        mock_user_obj.id = 999
        mock_user.return_value = mock_user_obj

        future = asyncio.Future()
        bot.pending_captchas[555] = future
        bot.latest_captcha_message_id = 555

        message = AsyncMock(spec=discord.Message)
        message.author.id = 111
        message.author.bot = False
        message.content = "ABCDEF"
        message.channel.id = 123
        message.reference = None

        # Mock history where previous message is NOT the captcha
        prev_msg = AsyncMock(spec=discord.Message)
        prev_msg.id = 99999  # Some other message

        async def mock_history_gen(*args, **kwargs):
            yield message
            yield prev_msg

        message.channel.history = mock_history_gen

        await bot.on_message(message)

        assert not future.done()
