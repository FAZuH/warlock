import asyncio
import io
import discord
from loguru import logger
from fazuh.warlock.config import Config


class CaptchaBot(discord.Client):
    def __init__(self, channel_id: int):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.channel_id = channel_id
        self.pending_captchas: dict[int, asyncio.Future] = {}
        self._ready_event = asyncio.Event()

    async def on_ready(self):
        logger.info(f"CaptchaBot logged in as {self.user}")
        self._ready_event.set()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        # Check if message is a reply
        if message.reference and message.reference.message_id in self.pending_captchas:
            future = self.pending_captchas[message.reference.message_id]
            if not future.done():
                solution = message.content.strip()
                logger.info(f"Received CAPTCHA solution from {message.author}")
                future.set_result(solution)
                try:
                    await message.add_reaction("✅")
                except Exception:
                    pass

    async def solve(self, image_data: bytes) -> str | None:
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


async def _get_or_create_bot() -> CaptchaBot | None:
    global _bot, _bot_task
    config = Config()

    if not config.discord_token or not config.discord_channel_id:
        return None

    # cast to int to be sure
    try:
        channel_id = int(config.discord_channel_id)
    except (ValueError, TypeError):
        logger.error("Invalid DISCORD_CHANNEL_ID")
        return None

    if _bot is None:
        _bot = CaptchaBot(channel_id)
        # Start the bot in background
        _bot_task = asyncio.create_task(_bot.start(config.discord_token))

        # Check for immediate failure (like invalid token)
        # Give it a small moment to potentially fail or start logging in
        await asyncio.sleep(0.1)
        if _bot_task.done() and _bot_task.exception():
            logger.error(f"Discord bot failed to start: {_bot_task.exception()}")
            _bot = None
            _bot_task = None
            return None

    return _bot


async def get_captcha_solution(image_data: bytes) -> str | None:
    bot = await _get_or_create_bot()
    if not bot:
        logger.warning("Discord bot not available.")
        return None

    return await bot.solve(image_data)
