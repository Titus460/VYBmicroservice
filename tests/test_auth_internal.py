import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.auth_client import get_user, get_users_batch
from Model.auth_db import DualWriteCursor, is_write_sql, rewrite_auth_sql
from Model.auth_service import AuthRegistrationService
from services.catalog import owner_of


def test_internal_auth_paths_belong_to_auth():
    assert owner_of("/registrationRoute/internal/get_user") == "auth"
    assert owner_of("/registrationRoute/internal/get_users_batch") == "auth"


def test_internal_key_rejects_wrong_header(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    service = AuthRegistrationService.__new__(AuthRegistrationService)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Internal-Key": "wrong"}):
        denied = service._require_internal_key()
    assert denied is not None
    body, status = denied
    assert status == 401
    assert body.get_json()["Status"] == "Failure"


def test_auth_client_posts_to_auth_service(monkeypatch):
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": "Success", "user": {"userId": 7, "fullName": "Ada"}}

    with patch("Model.auth_client.requests.post", return_value=FakeResponse()) as post:
        user = get_user(7)
    assert user["userId"] == 7
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://auth:8000/registrationRoute/internal/get_user"
    assert kwargs["json"] == {"userId": 7}
    assert kwargs["headers"]["X-Internal-Key"] == "secret"


def test_auth_client_batch_empty_list():
    assert get_users_batch([]) == []


def test_rewrite_auth_sql_only_auth_tables():
    sql = (
        "SELECT r.userId, p.profilePic FROM icebreaker.registration r "
        "JOIN icebreaker.profile p ON r.userId = p.userId"
    )
    rewritten = rewrite_auth_sql(sql, "vyb_auth")
    assert "vyb_auth.registration" in rewritten
    assert "icebreaker.profile" in rewritten
    assert rewrite_auth_sql(sql, "icebreaker") == sql


def test_dual_write_cursor_mirrors_updates():
    class Fake:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    fake = Fake()
    cursor = DualWriteCursor(fake, "vyb_auth")
    cursor.execute(
        "UPDATE icebreaker.registration SET deviceToken = NULL WHERE userId = %s",
        (9,),
    )
    assert fake.calls[0][0] == "UPDATE vyb_auth.registration SET deviceToken = NULL WHERE userId = %s"
    assert fake.calls[1][0] == "UPDATE icebreaker.registration SET deviceToken = NULL WHERE userId = %s"
    assert is_write_sql("SELECT 1") is False
