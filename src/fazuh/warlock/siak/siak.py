import asyncio
import base64
from collections.abc import Iterable
from typing import Any

from loguru import logger
from playwright.async_api import async_playwright
import requests

from fazuh.warlock.bot import get_captcha_solution
from fazuh.warlock.config import Config
from fazuh.warlock.siak.path import Path


class Siak:
    def __init__(self, config: Config, auth_max_retries: int = 5):
        self.config = config
        self.auth_max_retries = auth_max_retries

    async def start(self):
        """Start the browser"""
        self.playwright = await async_playwright().start()

        match self.config.browser:
            case "chromium":
                browser = self.playwright.chromium
            case "firefox":
                browser = self.playwright.firefox
            case "webkit":
                browser = self.playwright.webkit
            case _:
                logger.error(f"Unsupported browser: {self.config.browser}. Defaulting to Chromium.")
                browser = self.playwright.chromium

        launch_kwargs: dict[str, Any] = {"headless": self.config.headless}
        if self.config.browser == "brave":
            launch_kwargs["executable_path"] = "/usr/bin/brave"

        self.browser = await browser.launch(**launch_kwargs)
        self.page = await self.browser.new_page()

        if self.config.is_test:
            from fazuh.warlock.test_manager import TestManager

            await TestManager(self.config).setup_mocks(self.page)

    async def close(self):
        """Close the browser"""
        # NOTE: self.browser and self.playwright is created at self.start(), not self.__init__(),
        # thus there is no guarantee it is initialized yet.
        if hasattr(self, "browser"):
            await self.browser.close()
        if hasattr(self, "playwright"):
            await self.playwright.stop()

    async def restart(self):
        """Close, and restart the browser"""
        await self.close()
        await self.start()

    async def reload(self):
        """Refresh the current page"""
        await self.page.reload()

    async def authenticate(self, retries: int = 0) -> bool:
        if self.config.is_test:
            logger.info("Test mode enabled. Skipping authentication.")
            return True

        if retries > self.auth_max_retries:
            logger.error("Maximum authentication retries reached.")
            return False

        if await self.is_logged_in():
            return True  # Already logged in, no need to authenticate

        try:
            if not await self.is_login_page():
                await self.page.goto(Path.HOSTNAME)

            # Handle pre-login CAPTCHA page
            if await self.handle_captcha():
                # Captcha handled, retry auth immediately but increment count to be safe
                return await self.authenticate(retries + 1)

            await self.page.wait_for_load_state()
            # Proceed with standard login
            await self.page.locator("input[name=u]").click()
            await self.page.locator("input[name=u]").fill(self.config.username)

            await self.page.locator("input[name=p]").click()
            await self.page.locator("input[name=p]").fill(self.config.password)

            # Hover then click to simulate human interaction
            submit_btn = self.page.locator("input[type=submit]")
            await submit_btn.hover()
            await self.page.wait_for_timeout(200)

            async with self.page.expect_navigation(wait_until="networkidle"):
                await submit_btn.click()

            # Handle post-login CAPTCHA page (possible)
            if await self.handle_captcha():
                return await self.authenticate(retries + 1)

        except Exception as e:
            logger.error(f"An unexpected error occurred during authentication: {e}")
            # Don't retry immediately on exception to avoid tight loops, just return fail or let outer loop handle
            return False

        await self.page.wait_for_load_state()
        if await self.is_login_page():
            logger.warning(f"Still on login page after attempt {retries + 1}. Retrying...")
            await asyncio.sleep(1)
            return await self.authenticate(retries + 1)

        if not await self.handle_role_selection():
            return False

        if not await self.does_need_restart():
            await self.restart()
            return False

        if not await self.does_need_reload():
            await self.reload()
            return False

        logger.info("Authentication successful.")
        return True

    async def unauthenticate(self):
        """Logs out from the application."""
        if hasattr(self, "page"):
            await self.page.goto(Path.LOGOUT)
            logger.info("Logged out successfully.")

    async def does_need_restart(self) -> bool:
        """If this returns false, the browser should restart to clear sessions."""
        if await self.is_rejected_page():
            logger.error("The requested URL was rejected.")
            return False
        return True

    async def does_need_reload(self) -> bool:
        if await self.is_high_load_page():
            logger.error("The server is under high load. Please try again later.")
            return False
        if await self.is_inaccessible_page():
            logger.error("The page is currently inaccessible. Please try again later.")
            return False
        return True

    async def handle_role_selection(self) -> bool:
        """Handles role selection if no role is selected."""
        if await self.is_role_selected():
            return True

        logger.info("No role selected. Navigating to change role page.")
        await self.page.goto(Path.CHANGE_ROLE)

        if not await self.is_role_selected():
            logger.error("Failed to select a role. Please check your account settings.")
            return False

        return True

    async def handle_captcha(self) -> bool:
        """Extracts CAPTCHA, notifies admin, and gets solution from CLI."""
        await self.page.wait_for_load_state()
        if not await self.is_captcha_page():
            return False

        try:
            image_element = await self.page.query_selector('img[src*="data:image/png;base64,"]')
            if not image_element:
                raise ValueError("CAPTCHA image element not found.")

            image_src = await image_element.get_attribute("src")
            if not image_src or "base64," not in image_src:
                raise ValueError("Could not extract CAPTCHA image source.")

            base64_data = image_src.split(",", 1)[1]
            image_data = base64.b64decode(base64_data)

            captcha_solution = await get_captcha_solution(image_data)

            if captcha_solution:
                await self.page.fill("input[name=answer]", captcha_solution)
                await self.page.click("button#jar")
                await self.page.wait_for_load_state()
                return True

            # If no discord solution, and headless, we can't continue
            if self.config.headless:
                logger.error("CAPTCHA detected in HEADLESS mode. Discord Bot not configured.")
                raise Exception(
                    "Headless mode requires Discord Bot for CAPTCHA. Set HEADLESS=false to solve manually."
                )

            # Manual handling
            if self.config.auth_discord_webhook_url:
                await self._notify_admin_for_captcha(image_data)

            logger.warning(
                "CAPTCHA detected. Please solve it manually in the opened browser window."
            )

            # Poll until captcha is gone
            while True:
                try:
                    # Check if answer input is still visible
                    if not await self.page.is_visible("input[name=answer]"):
                        # Double check content logic to be safe
                        if not await self.is_captcha_page():
                            logger.success("CAPTCHA passed.")
                            break
                except Exception:
                    # Page possibly navigated away or closed
                    break
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Failed to handle CAPTCHA: {e}")
            raise

        return True

    async def is_not_registration_period(self, content: str | None = None) -> bool:
        """Check if the current period is not a registration period."""
        ret = await self._check_page_content(
            ["Anda tidak dapat mengisi IRS karena periode registrasi akademik belum dimulai"],
            content,
        )
        return ret

    async def is_login_page(self, content: str | None = None) -> bool:
        """Check if current page is the login page."""
        # return Path.AUTHENTICATION in self.page.url
        # NOTE: `self.page.url` be in `Path.AUTHENTICATION`, but the page shows "The request URL was rejected"
        return await self._check_page_content(["Waspada terhadap pencurian password!"], content)

    async def is_logged_in(self, content: str | None = None) -> bool:
        """Check if the user is logged in."""
        return await self._check_page_content(["Logout Counter"], content)

    async def is_role_selected(self, content: str | None = None) -> bool:
        """Check if a role is selected."""
        return not await self._check_page_content(["No role selected"], content)

    async def is_captcha_page(self, content: str | None = None) -> bool:
        """Check if the current page is a CAPTCHA page."""
        keywords = [
            "This question is for testing whether you are a human visitor",
            "What code is in the image?",
            "You have entered an invalid answer",
        ]
        return await self._check_page_content(keywords, content)

    async def is_rejected_page(self, content: str | None = None) -> bool:
        """Check if the current page is a rejected URL page."""
        return await self._check_page_content(["The requested URL was rejected"], content)

    async def is_high_load_page(self, content: str | None = None) -> bool:
        """Check if the current page indicates high server load."""
        # Maaf, server SIAKNG sedang mengalami load tinggi dan belum dapat melayani request Anda saat ini.
        # Silahkan mencoba beberapa saat lagi.
        return await self._check_page_content(
            ["server SIAKNG sedang mengalami load tinggi"], content
        )

    async def is_inaccessible_page(self, content: str | None = None) -> bool:
        """Check if the current page is inaccessible."""
        return await self._check_page_content(["Silakan mencoba beberapa saat lagi."], content)

    async def _check_page_content(
        self, keywords: Iterable[str], content: str | None = None
    ) -> bool:
        """Check if page contents contains a specific string"""
        if content is None:
            if not hasattr(self, "page"):
                return False
            content = await self.content
        return any(kw in content for kw in keywords)

    @property
    async def content(self) -> str:
        """Get the current page content."""
        return await self.page.content()

    async def _notify_admin_for_captcha(self, image_data: bytes):
        """Sends the CAPTCHA image to the admin webhook."""
        if not self.config.auth_discord_webhook_url:
            return

        message = "CAPTCHA detected. Please provide the solution."
        if self.config.user_id:
            message = f"<@{self.config.user_id}> {message}"

        try:
            files = {"file": ("captcha.png", image_data, "image/png")}
            data = {"username": "Warlock Auth", "content": message}
            response = await asyncio.to_thread(
                requests.post,
                self.config.auth_discord_webhook_url,
                data=data,
                files=files,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Admin notified about CAPTCHA and image sent.")
        except requests.RequestException as e:
            logger.error(f"Failed to notify admin via webhook: {e}")
