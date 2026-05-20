"""Shared pytest fixtures."""
import pytest


@pytest.fixture
def tmp_manifest_path(tmp_path):
    return tmp_path / "manifest.json"
