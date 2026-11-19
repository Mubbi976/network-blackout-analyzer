from fastapi.testclient import TestClient

from backend import main
from backend.config import Settings
from backend.main import app


def test_health_endpoint_reports_api_responsive() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_serves_working_ui_and_rejects_non_youtube_media_url() -> None:
    client = TestClient(app)

    page = client.get("/")
    invalid_metadata = client.post(
        "/api/metadata",
        json={"url": "https://example.com/watch?v=Abcdef12345"},
    )

    assert page.status_code == 200
    assert "Clip Studio" in page.text
    assert invalid_metadata.status_code == 422


def test_configured_access_key_protects_api_but_not_health_or_ui(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            _env_file=None,
            app_access_token="test-access-key",
            downloads_dir=tmp_path / "downloads",
            clips_dir=tmp_path / "clips",
            temp_dir=tmp_path / "temp",
            logs_dir=tmp_path / "logs",
            model_cache_dir=tmp_path / "models",
        ),
    )
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/jobs").status_code == 401
    authorized = client.get(
        "/api/jobs",
        headers={"Authorization": "Bearer test-access-key"},
    )
    assert authorized.status_code == 200
