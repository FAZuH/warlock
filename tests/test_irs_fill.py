from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from fazuh.warlock.model import CourseTarget
from fazuh.warlock.service.irs_service import IrsService
from fazuh.warlock.siak.siak import Siak


@pytest.fixture
def mock_siak():
    siak = MagicMock(spec=Siak)
    siak.page = MagicMock()
    siak.page.goto = AsyncMock()
    siak.page.url = "https://academic.ui.ac.id/main/CoursePlan/CoursePlanEdit"
    siak.is_not_registration_period = AsyncMock(return_value=False)
    return siak


@pytest_asyncio.fixture
async def irs_html():
    path = Path(__file__).parent / "mock" / "irs_page.html"
    return path.read_text(encoding="windows-1252")


@pytest.mark.asyncio
async def test_fill_irs_integration(mock_siak, irs_html):
    # Setup mock page content
    mock_siak.page.content = AsyncMock(return_value=irs_html)
    mock_siak.page.check = AsyncMock()

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(irs_html, "html.parser")
    rows = soup.find_all("tr")

    mock_data = []

    for row in rows:
        course_el = row.find("label")
        prof_els = row.find_all("td")
        radio_el = row.find("input", type="radio")

        if not course_el or len(prof_els) < 9 or not radio_el:
            continue

        mock_data.append(
            {
                "name": course_el.get_text(strip=True),
                "prof": prof_els[8].get_text(strip=True),
                "time": prof_els[6].get_text(strip=True),
                "code": radio_el.get("value"),
            }
        )

    mock_siak.page.evaluate = AsyncMock(return_value=mock_data)

    service = IrsService(mock_siak)

    targets = [
        CourseTarget(course="Analisis 1", prof="Putri"),
        CourseTarget(code="782396"),
        CourseTarget(course="AnDat Kategorik", time="Senin, 10.00-12.30"),
    ]

    success = await service.fill_irs(targets)

    assert success is True
    assert mock_siak.page.check.call_count == 3
