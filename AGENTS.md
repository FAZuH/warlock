# Warlock - Agent Guide

This repository hosts **Warlock**, a Python automation tool for university portals (SIAK UI), featuring course enrollment, schedule tracking, and IRS autofilling.

## 1. Environment & Build

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and command execution. **Do not use `pip` or `poetry` directly.**

### Setup
- **Install Dependencies:** `uv sync`
- **Install Playwright:** `uv run playwright install-deps && uv run playwright install`
- **Environment:** Copy `.env-example` to `.env`. **NEVER commit `.env`, `courses.json`, or `courses.yaml`.**

### Running the Application
- **Main Command:** `uv run warlock <command>` (e.g., `war`, `track`, `autofill`)
- **Direct Script:** `uv run python -m fazuh.warlock <command>`

### Testing
*Note: The `tests/` directory is configured in `pyproject.toml`.*

- **Run All Tests:** `uv run pytest`
- **Run Single Test:** `uv run pytest tests/path/to/test_file.py::test_function_name`
- **Run with Output:** `uv run pytest -s`

**Test Categories:**
- **Manual Tests (`tests/manual`):** These tests require manual interaction or specific data files. Run with `--run-manual`.
  - Example: `uv run pytest tests/manual/test_warbot_manual.py --run-manual --schedule-html "path/to/schedule.html"`
- **Webhook Tests (`tests/webhook`):** Tests for Discord webhook integration.
- **Full Tests**: Run ALL tests using `uv run pytest --run-webhook --run-manual --schedule-html="data/Jadwal Kelas Mata Kuliah - SIAK NG.html" -s`. This is the recommended way of testing to make sure nothing breaks

### Linting & Formatting
Strict adherence to `ruff` and `isort` configurations in `pyproject.toml` is required.

- **Check Linting:** `uv run ruff check .`
- **Fix Linting:** `uv run ruff check --fix .`
- **Format Code:** `uv run ruff format .`
- **Sort Imports:** `uv run isort .` (Profile: Google, Line length: 100 - per pyproject.tlml)

## 2. Code Style & Conventions

### General
- **Python Version:** 3.12+
- **Line Length:** 100 characters.
- **Indentation:** 4 spaces.
- **Quotes:** Double quotes (`"`) preferred.

### Imports
- **Sorting:** Managed by `isort` (Google profile).
- **Structure:**
  1. Standard Library (`import os`, `from datetime import ...`)
  2. Third-Party (`import discord`, `from loguru import logger`)
  3. Local Application (`from fazuh.warlock.config import Config`)

### Typing
- **Type Hints:** Strongly encouraged for all function signatures and complex variables.
- **Generics:** Use built-in generics (`list[str]`, `dict[str, Any]`) instead of `typing.List`.
- **MyPy:** If running type checks, ensure compatibility with strict mode.

### Naming
- **Variables/Functions:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_CASE`
- **Private Members:** `_prefix` (e.g., `_send_diff_to_webhook`)

### Logging & Error Handling
- **Logger:** Use **`loguru`** exclusively (`from loguru import logger`). Do not use the standard `logging` module.
- **Exceptions:** Catch specific exceptions (e.g., `requests.exceptions.RequestException`). Avoid bare `except Exception:`.
- **Async:** This project is heavily asynchronous (`asyncio`, `playwright`). Ensure proper `await` usage and `async def` definitions.

## 3. Architecture & Libraries

- **Browser Automation:** `playwright` (Async API).
  - **HTML Parsing:** `beautifulsoup4`.
- **HTTP Requests:** `httpx` (async) or `requests` (sync, legacy/simple). Prefer `httpx` for new async code.
- **Configuration:** `python-dotenv` for environment variables. `Config` class patterns are used for loading settings. `PyYAML` for advanced configuration.
- **Discord Integration:** `discord.py` for bot interactions and webhooks.

## 4. Agent Rules

1.  **Tool Usage:** Always use `uv run <command>` for shell operations.
2.  **File Paths:** Use absolute paths or correct relative paths from the project root.
3.  **Safety:**
    - Check for `courses.json` or `.env` before reading; handle their absence gracefully.
    - Never hardcode credentials.
4.  **Refactoring:** Run `uv run ruff check --fix .` and `uv run isort .` after making changes to ensure style compliance.
5.  **New Files:** When creating new modules, ensure they are within `src/fazuh/warlock/` and properly exported if necessary.
6.  **Documentation:** Update `README.md` whenever you modify user-facing features, configuration formats, or installation steps.
