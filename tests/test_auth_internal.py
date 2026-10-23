import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.auth_client import get_user, get_users_batch
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
