from typing import Dict, List, Set, TypedDict

from loguru import logger

from fazuh.warlock.module.schedule.parser import CourseInfo


class ChangeField(TypedDict):
    name: str
    value: str
    inline: bool


class Change(TypedDict):
    type: str  # "new", "removed", "modified"
    title: str
    fields: List[ChangeField]


class ClassDetail(TypedDict):
    waktu: str
    ruang: str
    dosen: str


def parse_classes_by_name(classes: List[str]) -> Dict[str, ClassDetail]:
    """Helper to parse class strings into structured dicts."""
    result = {}
    for class_detail in classes:
        parts = class_detail.split(";")
        if len(parts) >= 5:
            kelas = parts[0].replace("Kelas", "").strip()
            result[kelas] = {
                "waktu": parts[3].strip().lstrip("- "),
                "ruang": parts[4].strip().lstrip("- "),
                "dosen": parts[5].strip().lstrip("- ") if len(parts) > 5 else "-",
            }
    return result


def generate_diff(
    old: Dict[str, CourseInfo],
    new: Dict[str, CourseInfo],
    suppress_professor: bool = False,
    suppress_location: bool = False,
) -> List[Change]:
    """
    Generates a structured diff between old and new course data.

    Args:
        old: The previous course dictionary.
        new: The current course dictionary.
        suppress_professor: Whether to suppress changes that only involve professors.
        suppress_location: Whether to suppress changes that only involve locations.

    Returns:
        List of change objects.
    """
    changes: List[Change] = []

    # New courses
    for code in sorted(new.keys() - old.keys()):
        course_info = new[code]["info"]
        course_name = course_info.split(";")[0].strip()

        fields: List[ChangeField] = []
        for class_detail in new[code]["classes"]:
            parts = class_detail.split(";")
            if len(parts) >= 5:
                kelas = parts[0].replace("Kelas", "").strip()
                waktu = parts[3].strip().lstrip("- ")
                ruang = parts[4].strip().lstrip("- ")
                dosen = parts[5].strip().lstrip("- ") if len(parts) > 5 else "-"
                fields.append(
                    {
                        "name": kelas,
                        "value": f"- {waktu}\n- {ruang}\n- {dosen}",
                        "inline": False,
                    }
                )

        changes.append({"type": "new", "title": course_name, "fields": fields})

    # Removed courses
    for code in sorted(old.keys() - new.keys()):
        course_info = old[code]["info"]
        course_name = course_info.split(";")[0].strip()
        changes.append({"type": "removed", "title": course_name, "fields": []})

    # Modified courses
    for code in sorted(old.keys() & new.keys()):
        old_classes_dict = parse_classes_by_name(old[code]["classes"])
        new_classes_dict = parse_classes_by_name(new[code]["classes"])

        old_names = set(old_classes_dict.keys())
        new_names = set(new_classes_dict.keys())

        added_names = new_names - old_names
        removed_names = old_names - new_names
        common_names = old_names & new_names

        # Check for modifications within common classes
        modified_names: Set[str] = set()
        for name in common_names:
            old_info = old_classes_dict[name]
            new_info = new_classes_dict[name]

            if old_info == new_info:
                continue

            waktu_changed = old_info["waktu"] != new_info["waktu"]
            ruang_changed = old_info["ruang"] != new_info["ruang"]
            dosen_changed = old_info["dosen"] != new_info["dosen"]

            dosen_suppress = (
                suppress_professor and dosen_changed and not (waktu_changed or ruang_changed)
            )
            ruang_suppress = (
                suppress_location and ruang_changed and not (waktu_changed or dosen_changed)
            )

            # NOTE:
            # `dosen_suppress = True` IF AND ONLY IF all three conditions hold:
            # 1. `tracker_suppress_professor_change = True`
            # 2. `dosen_changed = True`
            # 3. `waktu_changed = False AND ruang_changed = False`
            #
            # Similar theorem also holds for `ruang_suppress`

            if dosen_suppress:
                logger.info(
                    f"Suppressed professor change at {name}: {old_info['dosen']} -> {new_info['dosen']}"
                )
                continue
            if ruang_suppress:
                logger.info(
                    f"Suppressed location change at {name}: {old_info['ruang']} -> {new_info['ruang']}"
                )
                continue

            modified_names.add(name)

        if not added_names and not removed_names and not modified_names:
            continue

        course_info = new[code]["info"]
        course_name = course_info.split(";")[0].strip()

        fields = []

        # Added classes
        for kelas in sorted(added_names):
            info = new_classes_dict[kelas]
            fields.append(
                {
                    "name": f"[+] ﻿ ﻿ ﻿  {kelas}",
                    "value": f"- {info['waktu']}\n- {info['ruang']}\n- {info['dosen']}",
                    "inline": False,
                }
            )

        # Modified classes
        for kelas in sorted(modified_names):
            old_info = old_classes_dict[kelas]
            new_info = new_classes_dict[kelas]

            # Show what changed
            lines = []
            if old_info["waktu"] != new_info["waktu"]:
                lines.append(f"- ~~{old_info['waktu']}~~ → {new_info['waktu']}")

            if old_info["ruang"] != new_info["ruang"]:
                lines.append(f"- ~~{old_info['ruang']}~~ → {new_info['ruang']}")

            if old_info["dosen"] != new_info["dosen"]:
                lines.append(f"- ~~{old_info['dosen']}~~ → {new_info['dosen']}")

            fields.append({"name": f"[Δ] ﻿ ﻿ ﻿ {kelas}", "value": "\n".join(lines), "inline": False})

        # Removed classes
        for kelas in sorted(removed_names):
            info = old_classes_dict[kelas]
            fields.append(
                {
                    "name": f"[−] ﻿ ﻿ ﻿  {kelas}",
                    "value": f"- ~~{info['waktu']}~~\n- ~~{info['ruang']}~~\n- ~~{info['dosen']}~~",
                    "inline": False,
                }
            )

        changes.append({"type": "modified", "title": course_name, "fields": fields})

    return changes
