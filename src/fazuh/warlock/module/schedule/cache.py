import asyncio
from pathlib import Path


class ScheduleCache:
    """Manages the storage and retrieval of the last known schedule state."""

    def __init__(self, file_path: str | Path = "data/latest_courses.txt"):
        self.file_path = Path(file_path)
        self._ensure_directory()

    def _ensure_directory(self):
        """Ensures the directory for the cache file exists."""
        if not self.file_path.parent.exists():
            self.file_path.parent.mkdir(parents=True)

    def exists(self) -> bool:
        """Checks if the cache file exists."""
        return self.file_path.exists()

    def read(self) -> str:
        """Reads the cache file content."""
        if self.exists():
            return self.file_path.read_text(encoding="utf-8")
        return ""

    async def write(self, content: str):
        """Writes content to the cache file asynchronously."""
        await asyncio.to_thread(self.file_path.write_text, content, encoding="utf-8")

    def touch(self):
        """Creates the file if it doesn't exist."""
        self.file_path.touch()
