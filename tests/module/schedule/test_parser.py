import pytest

from fazuh.warlock.module.schedule.parser import parse_schedule_html
from fazuh.warlock.module.schedule.parser import parse_schedule_string
from fazuh.warlock.module.schedule.parser import serialize_schedule

HTML_SAMPLE = """
<table>
    <tr>
        <th class="sub border2 pad2"><strong>CS101 - Intro to CS</strong></th>
    </tr>
    <tr>
        <td>1</td>
        <td>Kelas A</td>
        <td>English</td>
        <td>25/08/2025 - 19/12/2025</td>
        <td>Mon, 08.00-09.40</td>
        <td>Room 101</td>
        <td>- Dr. Smith</td>
    </tr>
    <tr>
        <th class="sub border2 pad2"><strong>CS102 - Data Structures</strong></th>
    </tr>
    <tr>
        <td>1</td>
        <td>Kelas B</td>
        <td>Indonesia</td>
        <td>25/08/2025 - 19/12/2025</td>
        <td>Tue, 10.00-11.40</td>
        <td>Room 102</td>
        <td>- Dr. Doe</td>
    </tr>
</table>
"""


def test_parse_schedule_html():
    result = parse_schedule_html(HTML_SAMPLE)

    assert "CS101" in result
    assert "CS102" in result

    cs101 = result["CS101"]
    assert cs101["info"] == "CS101 - Intro to CS"
    assert len(cs101["classes"]) == 1
    assert "Kelas A" in cs101["classes"][0]
    assert "Dr. Smith" in cs101["classes"][0]


def test_serialize_and_parse_string():
    data = {
        "CS101": {
            "info": "CS101 - Intro to CS",
            "classes": ["Kelas A; English; Date; Time; Room; Prof"],
        }
    }

    serialized = serialize_schedule(data)
    assert "CS101 - Intro to CS: | Kelas A" in serialized

    parsed = parse_schedule_string(serialized)
    assert parsed == data


def test_parse_schedule_string_no_classes():
    content = "CS101 - Intro to CS"
    parsed = parse_schedule_string(content)

    assert "CS101" in parsed
    assert parsed["CS101"]["classes"] == []
