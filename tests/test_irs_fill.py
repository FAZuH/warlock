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

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(irs_html, "html.parser")
    rows = soup.find_all("tr")

    mock_rows = []
    mock_query_results = {}

    for i, row in enumerate(rows):
        m_row = MagicMock()
        m_row_id = i

        async def mq(sel, r=row, rid=m_row_id):
            key = (rid, sel)
            if key in mock_query_results:
                return mock_query_results[key]

            res = None
            if sel == "label":
                l = r.find("label")
                if l:
                    res = MagicMock()
                    res.inner_text = AsyncMock(return_value=l.get_text(strip=True))
            elif sel == "td:nth-child(9)":
                tds = r.find_all("td")
                if len(tds) >= 9:
                    res = MagicMock()
                    res.inner_text = AsyncMock(return_value=tds[8].get_text(strip=True))
            elif sel == "td:nth-child(7)":
                tds = r.find_all("td")
                if len(tds) >= 7:
                    res = MagicMock()
                    res.inner_text = AsyncMock(return_value=tds[6].get_text(strip=True))
            elif sel == 'input[type="radio"]':
                inp = r.find("input", type="radio")
                if inp:
                    res = MagicMock()
                    res.get_attribute = AsyncMock(return_value=inp.get("value"))
                    res.check = AsyncMock()

            mock_query_results[key] = res
            return res

        m_row.query_selector = AsyncMock(side_effect=mq)
        mock_rows.append(m_row)

    mock_siak.page.query_selector_all = AsyncMock(return_value=mock_rows)

    service = IrsService()

    targets = [
        CourseTarget(course="Analisis 1", prof="Putri"),
        CourseTarget(code="782396"),
        CourseTarget(course="AnDat Kategorik", time="Senin, 10.00-12.30"),
    ]

    success = await service.fill_irs(mock_siak, targets)

    assert success is True

    checked_count = sum(
        1 for res in mock_query_results.values() if hasattr(res, "check") and res.check.called
    )
    assert checked_count == 3
