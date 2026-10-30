"""Every test gets a fresh in-memory turbopuffer and settings pointing at it. No keys, no network."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpdesk import config, tpuf  # noqa: E402
from tests.fakes import FakeTurbopuffer  # noqa: E402


@pytest.fixture
def fake_tpuf():
    f = FakeTurbopuffer()
    yield f
    f.close()


@pytest.fixture
def settings(fake_tpuf, monkeypatch):
    monkeypatch.setenv("TURBOPUFFER_API_KEY", "test-key")
    monkeypatch.setenv("TURBOPUFFER_BASE_URL", fake_tpuf.url)
    monkeypatch.setenv("APP_PASSWORD", "test-password")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return config.load()


@pytest.fixture
def client(settings):
    return tpuf.client(settings)


@pytest.fixture
def library(client, settings):
    from helpdesk import seed
    return seed.load_sample_library(client, settings)
