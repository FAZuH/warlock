
https://github.com/user-attachments/assets/31b86a47-ba8f-466b-8d71-48ab0384e73e

https://github.com/user-attachments/assets/e1f077d2-494c-43de-b5be-4a1bfbb87a3d

> [!warning]
> This script may not work as expected. Use at your own risk.

## Features

- Automatic authentication to university portal
- Handle CAPTCHA challenges via CLI or interactive Discord bot
- Send notifications via Discord webhook

**Modules**:
- **war**: Bot to search and enroll for courses by course and professor names.
- **track**: Track changes in course offerings, including professor, schedule, location, and more.
- **autofill**: Automates IRS filling after manual authentication.

## Installation

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. Download/clone this repository

In root of the repository,

3. Run `uv sync`. (This will install all the required project dependencies and set up the project environment)
4. Run `uv run playwright install-deps && uv run playwright install`. (This will install the necessary dependencies for Playwright, which is used for web scraping and automation)
5. Copy `.env-example` file to `.env` and fill in the required environment variables. Each variable is documented in the `.env-example` file.

## Usage

### War bot

Create a `courses.yaml` (recommended) or `courses.json` file to configure your target courses.

**Recommended Format (`courses.yaml`):**
```yaml
# Select by Course only (chooses the first match)
- course: Database

# Select by Course and Professor
- course: Analisis Mult
  prof: Titin

# Select by Class Code (unique ID in radio button value)
- code: "782396"

# Select by Course and Time
- course: Agama Buddha
  time: Jumat

# You can add names for your own reference
- name: "My Favorite Elective"
  code: "785627"
```

You can run using `uv run warlock war`.

The War bot supports flexible matching criteria (case-insensitive partial matches):
- **Course & Professor**: Matches course name and professor name.
- **Class Code**: Matches the unique class code (radio button value).
- **Time**: Matches course name and schedule time.
- **Legacy JSON**: `{"Course Name": "Prof Name"}` format is still supported for backward compatibility.

### Schedule update tracker

In root of the repository, run `uv run warlock track`.

### AutoFill

This module helps you fill the IRS form quickly after you log in manually. It is useful when you want to handle the login process yourself but want the bot to select courses for you.

1. Configure `courses.json` as described in the War bot section.
2. Run `uv run warlock autofill`.
3. A browser window will open. Log in and select your role manually.
4. Once you are in, the bot will automatically navigate to the IRS page, fill in the courses, and scroll to the bottom.
5. You can then review and submit manually.

### Discord Bot for CAPTCHA

You can configure a Discord bot to handle CAPTCHA challenges remotely.

1. Create a Discord Bot and get the token.
2. Invite the bot to your server.
3. Get the Channel ID where you want the bot to post.
4. Set **BOTH** `DISCORD_TOKEN` and `DISCORD_CHANNEL_ID` in your `.env`.

When a CAPTCHA appears, the bot will post the image to the channel. **Reply** to the bot's message with the solution code to solve it.

**NOTE**: If you do not configure the Discord Bot, you must set `HEADLESS=false` in your `.env`. The browser window will open, and you will need to solve the CAPTCHA manually in the browser when prompted.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
