from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_unhandled_request_crash_is_redacted_and_reported(tmp_path, caplog):
    app = create_app(Settings(database_path=str(tmp_path / "crash.db")))

    @app.get("/test/crash")
    def crash():
        raise RuntimeError("private input must not reach logs")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test/crash?secret=private")
    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred"}
    assert response.headers["Cache-Control"] == "no-store"
    assert "backend_unhandled_exception" in caplog.text
    assert "private" not in caplog.text
