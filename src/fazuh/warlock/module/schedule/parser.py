from typing import Dict, List, TypedDict

from bs4 import BeautifulSoup
from bs4 import Tag


class CourseInfo(TypedDict):
    info: str
    classes: List[str]


def parse_schedule_html(html_content: str) -> Dict[str, CourseInfo]:
    """
    Parses the SIAK schedule HTML into a structured dictionary.

    Args:
        html_content: The raw HTML string.

    Returns:
        A dictionary where keys are course codes and values contain info and list of class strings.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    result: Dict[str, CourseInfo] = {}

    # every course starts with <th class="sub ...">
    for hdr in soup.find_all("th", class_=("sub", "border2", "pad2")):
        if hdr.parent is None:
            continue

        # 2a. course header
        course_line = hdr.get_text(strip=True)
        course_line = course_line.replace("<strong>", "").replace("</strong>", "")

        # Extract course code (first part before the dash)
        # Example: "CS123 - Intro to CS" -> "CS123"
        course_code = course_line.split("-")[0].strip()

        # 2b. collect all following <tr> rows that belong to this course
        classes_info = []
        for sibling in hdr.parent.find_next_siblings("tr"):
            if not isinstance(sibling, Tag):
                continue

            # stop if we hit the next course header
            if sibling.find("th", class_=("sub", "border2", "pad2")):
                break

            # collect the text of every <td> in this <tr>
            cells = [td.get_text(strip=True) for td in sibling.find_all("td")]
            if not cells:
                continue

            # build one line per class, e.g.
            # "Kelas Teori Matriks (A); Indonesia; 25/08/2025 - 19/12/2025; Rabu, 08.00-09.40; D.109; - Dra. ..."
            class_line = "; ".join(cells[1:])  # skip the first cell (index number)
            classes_info.append(class_line)

        result[course_code] = {"info": course_line, "classes": classes_info}

    return result


def serialize_schedule(schedule: Dict[str, CourseInfo]) -> str:
    """
    Serializes the schedule dictionary to the legacy string format for caching.

    Format: "Course Info: | Class 1 | Class 2"
    """
    lines = []
    for _, data in schedule.items():
        course_line = data["info"]
        classes_info = data["classes"]

        full_entry = (
            f"{course_line}: | " + " | ".join(classes_info) if classes_info else course_line
        )
        lines.append(full_entry)

    return "\n".join(lines)


def parse_schedule_string(content: str) -> Dict[str, CourseInfo]:
    """
    Parses the legacy string format back into the dictionary structure.
    Used for reading the cache file.
    """
    result: Dict[str, CourseInfo] = {}
    for line in content.splitlines():
        if not line.strip():
            continue

        if ": |" in line:
            course_info, classes_str = line.split(": |", 1)
            course_code = course_info.split("-")[0].strip()
            classes = [c.strip() for c in classes_str.split(" | ") if c.strip()]
            result[course_code] = {"info": course_info, "classes": classes}
        else:
            # Case where there are no classes, just the course info
            course_info = line.strip()
            course_code = course_info.split("-")[0].strip()
            result[course_code] = {"info": course_info, "classes": []}

    return result
