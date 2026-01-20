import os
from typing import Self

from dotenv import load_dotenv
from loguru import logger
import requests


class Config:
    _instance: Self | None = None
    is_test: bool
    jadwal_html_path: str | None

    def load(self):
        """Load environment variables

        The priority is .env file > environment variables
        See .env-example for the required variables
        """
        load_dotenv()
        username = os.getenv("USERNAME")
        password = os.getenv("PASSWORD")
        if username is None or password is None:
            logger.error("USERNAME and PASSWORD environment variables are not set.")
            return

        tracker_webhook = os.getenv("TRACKER_DISCORD_WEBHOOK_URL")
        if tracker_webhook is None or not self._is_webhook_valid(tracker_webhook):
            logger.error("Invalid TRACKER_DISCORD_WEBHOOK_URL.")
            return

        tracked_url = os.getenv("TRACKED_URL")
        if tracked_url is None:
            logger.error("TRACKED_URL environment variable is not set.")
            return

        self.user_id = os.getenv("USER_ID")
        self.auth_discord_webhook_url = os.getenv("AUTH_DISCORD_WEBHOOK_URL")
        self.discord_token = os.getenv("DISCORD_TOKEN")
        self.discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
        if self.discord_channel_id:
            self.discord_channel_id = int(self.discord_channel_id)
        self.headless = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
        self.browser = os.getenv("BROWSER", "chromium").lower()

        # SiakNG credentials
        self.username = username
        self.password = password

        # Schedule update tracker
        self.tracker_interval = int(os.getenv("TRACKER_INTERVAL", 1200))
        self.tracked_url = tracked_url
        self.tracker_discord_webhook_url = tracker_webhook

        # War bot
        self.warbot_interval = int(os.getenv("WARBOT_INTERVAL", 5))
        self.warbot_autosubmit = os.getenv("WARBOT_AUTOSUBMIT", "true").lower() in (
            "true",
            "1",
            "yes",
        )

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)

            # Test mode defaults
            cls._instance.is_test = False
            cls._instance.jadwal_html_path = None

            cls._instance.load()
        return cls._instance

    @staticmethod
    def _is_webhook_valid(url: str) -> bool:
        try:
            resp = requests.head(url, timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False
