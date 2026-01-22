import os
from typing import Self

from dotenv import load_dotenv
from loguru import logger
import requests


class Config:
    """Application configuration manager.

    Handles loading and validation of environment variables and configuration settings
    for the Warlock application, including credentials, browser settings, and
    Discord integration.
    """

    _instance: Self | None = None

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
        self.headless = self._is_truthy(os.getenv("HEADLESS", "true"))
        self.browser = os.getenv("BROWSER", "chromium").lower()

        # SiakNG credentials
        self.username = username
        self.password = password

        # Schedule update tracker
        self.tracker_interval = int(os.getenv("TRACKER_INTERVAL", 1200))
        self.tracked_url = tracked_url
        self.tracker_discord_webhook_url = tracker_webhook
        self.tracker_suppress_professor_change = self._is_truthy(
            os.getenv("TRACKER_SUPPRESS_PROFESSOR_CHANGE", "false")
        )
        self.tracker_suppress_location_change = self._is_truthy(
            os.getenv("TRACKER_SUPPRESS_LOCATION_CHANGE", "false")
        )

        # War bot
        self.warbot_interval = int(os.getenv("WARBOT_INTERVAL", 5))
        self.warbot_autosubmit = self._is_truthy(os.getenv("WARBOT_AUTOSUBMIT", "true"))
        self.warbot_notfound_retry = self._is_truthy(os.getenv("WARBOT_NOTFOUND_RETRY", "true"))

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)

            cls._instance.load()
        return cls._instance

    @staticmethod
    def _is_webhook_valid(url: str) -> bool:
        try:
            resp = requests.head(url, timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _is_truthy(self, bool_value: str) -> bool:
        return bool_value.lower() in (
            "true",
            "1",
            "yes",
        )
