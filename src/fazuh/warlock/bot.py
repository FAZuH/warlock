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
        self.latest_captcha_message_id: int | None = None

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

        bot_message_id = await self._identify_captcha_request(message)

        if bot_message_id:
            await self._handle_solution(message, bot_message_id)

    async def _identify_captcha_request(self, message: discord.Message) -> int | None:
        """Identifies if a message is a solution to a pending captcha."""
        # 1. Check direct reply
        if message.reference and message.reference.message_id in self.pending_captchas:
            return message.reference.message_id

        # 2. Check fallback (6 chars, correct channel, user message)
        if (
            message.channel.id == self.channel_id
            and len(message.content.strip()) == 6
            and not message.author.bot
            and self.pending_captchas
            and self.latest_captcha_message_id
        ):
            # Verify it's immediately after the latest captcha
            if await self._is_immediately_after_captcha(message):
                return self.latest_captcha_message_id

        return None

    async def _is_immediately_after_captcha(self, message: discord.Message) -> bool:
        """Checks if the message is immediately after the latest captcha message."""
        try:
            # Get history limit=2 (current message + previous one)
            messages = [msg async for msg in message.channel.history(limit=2)]

            if len(messages) < 2:
                return False

            # messages[0] is the current message (the solution candidate)
            # messages[1] should be the captcha message
            previous_message = messages[1]

            return previous_message.id == self.latest_captcha_message_id

        except Exception as e:
            logger.error(f"Failed to check message history: {e}")
            return False

    async def _handle_solution(self, message: discord.Message, bot_message_id: int):
        """Processes the solution message."""
        future = self.pending_captchas.get(bot_message_id)
        if future and not future.done():
            solution = message.content.strip()
            logger.info(f"Received CAPTCHA solution from {message.author}")
            future.set_result(solution)

            try:
                channel = message.channel
                bot_message = await channel.fetch_message(bot_message_id)
                await bot_message.add_reaction("✅")
            except Exception as e:
                logger.error(f"Failed to add reaction to bot message: {e}")

    async def solve(self, image_data: bytes) -> str | None:
        """Sends a CAPTCHA image to Discord and waits for a solution."""
        await self._ready_event.wait()

        channel = self.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except Exception:
                pass

        if not channel or not isinstance(channel, Messageable):
            logger.error(f"Channel {self.channel_id} not found or not messageable.")
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
            self.latest_captcha_message_id = message.id

            try:
                return await future
            finally:
                self.pending_captchas.pop(message.id, None)
                if self.latest_captcha_message_id == message.id:
                    self.latest_captcha_message_id = None

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
    channel_id = config.discord_channel_id

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
