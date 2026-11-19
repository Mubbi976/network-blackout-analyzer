from fastapi.testclient import TestClient

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
