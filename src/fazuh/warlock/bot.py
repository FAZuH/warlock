import asyncio
import io

import discord
from discord.abc import Messageable
from loguru import logger

from fazuh.warlock.config import Config


class CaptchaBot(discord.Client):
    """Discord bot for handling CAPTCHA challenges.

    This bot sends CAPTCHA images to a specified Discord channel and waits for
    a user to reply with the solution. It facilitates manual CAPTCHA solving
    for the automated browser session.
    """

    def __init__(self, channel_id: int):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.channel_id = channel_id
        self.pending_captchas: dict[int, asyncio.Future] = {}
        self._ready_event = asyncio.Event()

    async def on_ready(self):
        """Called when the bot has successfully connected to Discord."""
        logger.info(f"CaptchaBot logged in as {self.user}")
        self._ready_event.set()

    async def on_message(self, message: discord.Message):
        """Handles incoming messages.

        Checks if a message is a reply to a pending CAPTCHA request. If so,
        it extracts the solution and resolves the corresponding future.
        """
        if message.author == self.user:
            return

        # Check if message is a reply
        if message.reference and message.reference.message_id in self.pending_captchas:
            future = self.pending_captchas[message.reference.message_id]
            if not future.done():
                solution = message.content.strip()
                logger.info(f"Received CAPTCHA solution from {message.author}")
                future.set_result(solution)

                # Get the original bot message and add reaction to it
                try:
                    channel = message.channel
                    bot_message = await channel.fetch_message(message.reference.message_id)
                    await bot_message.add_reaction("✅")
                except Exception as e:
                    logger.error(f"Failed to add reaction to bot message: {e}")

    async def solve(self, image_data: bytes) -> str | None:
        """Sends a CAPTCHA image to Discord and waits for a solution.

        Args:
            image_data: The raw bytes of the CAPTCHA image.

        Returns:
            str | None: The solution string provided by the user, or None if failed.
        """
        # Wait for bot to be ready
        await self._ready_event.wait()

        channel = self.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except Exception:
                pass

        if not channel:
            logger.error(f"Channel {self.channel_id} not found.")
            return None

        if not isinstance(channel, Messageable):
            logger.error(f"Channel {self.channel_id} is not messageable.")
            return None

        try:
            file = discord.File(io.BytesIO(image_data), filename="captcha.png")
            message = await channel.send(
                content="CAPTCHA detected. Please **reply** to this message with the solution code.",
                file=file,
            )

            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self.pending_captchas[message.id] = future

            try:
                # Wait for solution
                return await future
            finally:
                self.pending_captchas.pop(message.id, None)

        except Exception as e:
            logger.error(f"Failed to solve CAPTCHA via Discord: {e}")
            return None


# Global Singleton state
_bot: CaptchaBot | None = None
_bot_task: asyncio.Task | None = None
_initialization_attempted: bool = False


def init_discord_bot():
    """Initializes the Discord bot if config is valid.

    Reads configuration from the global Config instance and starts the bot
    in a background task if the token and channel ID are present.
    """
    global _bot, _bot_task, _initialization_attempted

    if _initialization_attempted:
        return

    _initialization_attempted = True
    config = Config()

    token = config.discord_token
    # config.discord_channel_id is already int or None
    channel_id = config.discord_channel_id

    # Check config validity
    if token and channel_id:
        try:
            _bot = CaptchaBot(int(channel_id))
            _bot_task = asyncio.create_task(_bot.start(token))
            logger.info("Discord bot initialized in background.")
        except Exception as e:
            logger.error(f"Failed to initialize Discord bot: {e}")
            _bot = None
    elif token or channel_id:
        logger.warning(
            "Discord Bot configuration incomplete. Both DISCORD_TOKEN and DISCORD_CHANNEL_ID are required. Bot disabled."
        )
    else:
        logger.info(
            "Both DISCORD_TOKEN and DISCORD_CHANNEL_ID is empty. Skipped bot initialization."
        )


async def get_captcha_solution(image_data: bytes) -> str | None:
    """Request a CAPTCHA solution via the Discord bot.

    Ensures the bot is initialized before attempting to solve.

    Args:
        image_data: The raw bytes of the CAPTCHA image.

    Returns:
        str | None: The solution string, or None if the bot is not available.
    """
    # Ensure init was attempted
    if not _initialization_attempted:
        init_discord_bot()

    if not _bot:
        return None

    return await _bot.solve(image_data)
