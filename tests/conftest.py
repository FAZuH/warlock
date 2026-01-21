import pytest


def pytest_addoption(parser):
    parser.addoption("--run-manual", action="store_true", default=False, help="run manual tests")
    parser.addoption("--run-webhook", action="store_true", default=False, help="run webhook tests")
    parser.addoption(
        "--schedule-html",
        action="store",
        default=None,
        help="path to schedule html for manual tests",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "manual: mark test as manual to run")
    config.addinivalue_line("markers", "webhook: mark test as webhook test to run")


def pytest_collection_modifyitems(config, items):
    skip_manual = pytest.mark.skip(reason="need --run-manual option to run")
    skip_webhook = pytest.mark.skip(reason="need --run-webhook option to run")

    run_manual = config.getoption("--run-manual")
    run_webhook = config.getoption("--run-webhook")

    for item in items:
        if "manual" in item.keywords and not run_manual:
            item.add_marker(skip_manual)
        if "webhook" in item.keywords and not run_webhook:
            item.add_marker(skip_webhook)


@pytest.fixture
def schedule_html(request):
    path = request.config.getoption("--schedule-html")
    if not path:
        pytest.fail("--schedule-html option is required for this test")
    return path
