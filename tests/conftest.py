from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    data_dir = tmp_path / "lifeos-data"
    monkeypatch.setenv("LIFE_OS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LIFE_OS_AI_ENABLED", "false")

    from lifeos.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    from lifeos.main import create_app

    app = create_app(settings)
    with TestClient(app) as client:
        yield client, settings
    get_settings.cache_clear()
    os.environ.pop("LIFE_OS_DATA_DIR", None)


@pytest.fixture
def client(app_context):
    client, _settings = app_context
    response = client.post("/api/session")
    assert response.status_code == 200
    return client


@pytest.fixture
def settings(app_context):
    _client, settings = app_context
    return settings
