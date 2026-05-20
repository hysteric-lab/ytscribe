"""Opt-in integration test against real YouTube. Run with: pytest -m integration"""
import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("YTSCRIBE_INTEGRATION") != "1",
        reason="set YTSCRIBE_INTEGRATION=1 to run network integration tests",
    ),
]


def test_scan_a_real_video():
    from ytscribe.cli import _scan_to_manifest
    # a stable, public, captioned video
    manifest = _scan_to_manifest("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert manifest.summary()["total"] == 1
    assert manifest.videos[0].id == "jNQXAC9IVRw"
