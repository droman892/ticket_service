from fastapi.testclient import TestClient

from src.main import app


def test_app_boots_and_serves_openapi_schema() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Ticket Service"
