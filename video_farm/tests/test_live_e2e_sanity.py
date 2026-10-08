"""Explicitly opt-in, read-only HTTP smoke; never submit paid generation."""
import os
import runpy
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("VIDEO_FARM_LIVE_E2E") != "1",
    reason="Opt-in live HTTP check; unit tests remain fully isolated",
)


def test_live_http_readonly_smoke():
    # Keep the historical env flag/file name for compatibility, but do not
    # create workflows, use fake asset paths, or enqueue provider work here.
    script = Path(__file__).resolve().parents[2] / "run_e2e_verification.py"
    helper = runpy.run_path(str(script), run_name="readonly_smoke")
    report = helper["verify_service"](
        os.environ.get("VIDEO_FARM_SMOKE_URL", "http://127.0.0.1:8088")
    )
    assert report["read_only"] is True
    assert report["generation_verified"] is False
