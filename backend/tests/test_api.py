from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_status_and_flags():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "demo_mode" in body
    assert "llm_judgment" in body


def test_brief_requires_ingested_filing():
    response = client.get("/company/ZZZZ/filings/latest/brief")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_question_requires_minimum_length():
    response = client.post(
        "/company/NVDA/filings/latest/questions",
        json={"question": "short"},
    )
    assert response.status_code == 404
