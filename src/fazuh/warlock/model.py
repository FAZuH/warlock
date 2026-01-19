from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional

from loguru import logger
import yaml


@dataclass
class CourseTarget:
    course: Optional[str] = None
    prof: Optional[str] = None
    code: Optional[str] = None
    time: Optional[str] = None
    name: Optional[str] = None

    def matches(self, row_data: dict[str, str]) -> bool:
        """
        Checks if the provided row data matches this course target.
        row_data must contain keys corresponding to the fields: 'name' (course name from UI), 'prof', 'code', 'time'.
        """
        # 1. Match by Code (if provided, it is standalone or an override)
        if self.code:
            if row_data.get("code", "").startswith(self.code):
                return True
            return False

        # 2. Match by Course (Required if code is not provided)
        if not self.course:
            return False

        if self.course.lower() not in row_data.get("name", "").lower():
            return False

        # 3. Optional further filters: Professor
        if self.prof:
            if self.prof.lower() not in row_data.get("prof", "").lower():
                return False

        # 4. Optional further filters: Time
        if self.time:
            if self.time.lower() not in row_data.get("time", "").lower():
                return False

        return True

    def __repr__(self):
        parts = []
        if self.name:
            parts.append(f"[{self.name}]")
        if self.course:
            parts.append(f"Course: {self.course}")
        if self.prof:
            parts.append(f"Prof: {self.prof}")
        if self.code:
            parts.append(f"Code: {self.code}")
        if self.time:
            parts.append(f"Time: {self.time}")
        return " ".join(parts)


def load_courses() -> list[CourseTarget]:
    yaml_path = Path("courses.yaml")
    json_path = Path("courses.json")

    data = None

    if yaml_path.exists():
        logger.info(f"Loading courses from {yaml_path}")
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
    elif json_path.exists():
        logger.info(f"Loading courses from {json_path}")
        with open(json_path, "r") as f:
            data = json.load(f)
    else:
        logger.error("No courses configuration file found (courses.yaml or courses.json).")
        raise FileNotFoundError("courses.yaml or courses.json not found.")

    targets = []

    # Handle Legacy Dict Format: {"CourseName": "ProfName"}
    if isinstance(data, dict):
        logger.info("Detected legacy dictionary format. Converting to CourseTarget objects.")
        for name, prof in data.items():
            targets.append(CourseTarget(course=name, prof=prof))

    # Handle List Format (New Style)
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            # Convert string code to string if it was parsed as int by YAML/JSON
            if "code" in item:
                item["code"] = str(item["code"])

            targets.append(CourseTarget(**item))

    logger.info(f"Loaded {len(targets)} course targets.")
    return targets
