import pytest

from fazuh.warlock.module.auto_fill import AutoFill
from tests.libs.test_manager import MockManager


@pytest.mark.manual
@pytest.mark.asyncio
async def test_autofill_manual(schedule_html):
    autofill = AutoFill()
    autofill.conf.is_test = False

    await autofill.siak.start()

    try:
        mock_manager = MockManager(schedule_html)
        await mock_manager.setup_mocks(autofill.siak.page)

        # We skip auth by calling _run directly
        await autofill._run()

    finally:
        await autofill.siak.close()
