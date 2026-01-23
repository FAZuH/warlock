from fazuh.warlock.module.schedule.diff import generate_diff


def test_generate_diff_new_course():
    old = {}
    new = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }

    changes = generate_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "new"
    assert changes[0]["title"] == "CS101 - Intro to CS"
    assert len(changes[0]["fields"]) == 1
    assert changes[0]["fields"][0]["name"] == "A"


def test_generate_diff_removed_course():
    old = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }
    new = {}

    changes = generate_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "removed"
    assert changes[0]["title"] == "CS101 - Intro to CS"


def test_generate_diff_modified_class():
    old = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }
    new = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; NewTime; Room; Prof"],
        }
    }

    changes = generate_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "modified"
    assert len(changes[0]["fields"]) == 1
    assert "[Δ]" in changes[0]["fields"][0]["name"]
    assert "NewTime" in changes[0]["fields"][0]["value"]


def test_generate_diff_suppress_professor():
    old = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }
    new = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; NewProf"],
        }
    }

    # Without suppression
    changes = generate_diff(old, new, suppress_professor=False)
    assert len(changes) == 1

    # With suppression
    changes = generate_diff(old, new, suppress_professor=True)
    assert len(changes) == 0


def test_generate_diff_suppress_location():
    old = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }
    new = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; NewRoom; Prof"],
        }
    }

    # Without suppression
    changes = generate_diff(old, new, suppress_location=False)
    assert len(changes) == 1

    # With suppression
    changes = generate_diff(old, new, suppress_location=True)
    assert len(changes) == 0
