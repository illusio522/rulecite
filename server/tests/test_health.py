from fastapi.testclient import TestClient

from rulecite.main import app


def test_health_returns_ok():
    """서버가 실행 중이면 /health는 200과 ok 상태를 돌려준다."""
    # given
    client = TestClient(app)

    # when
    response = client.get("/health")

    # then
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
