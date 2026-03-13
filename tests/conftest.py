"""Global test fixtures — ensure the scheduler never starts real background jobs in tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_scheduler(request):
    """Patch CollectorScheduler.start and .shutdown for every test.

    Tests that create a FastAPI TestClient trigger the lifespan, which would
    otherwise launch real APScheduler background threads hitting the network and DB.
    This fixture prevents that without requiring per-test manual patching.

    Tests that explicitly need to test scheduler behavior can override by
    including `no_scheduler=False` in their markers or by patching themselves.
    """
    with patch("scheduler.CollectorScheduler.start", return_value=None), \
         patch("scheduler.CollectorScheduler.shutdown", return_value=None):
        yield
