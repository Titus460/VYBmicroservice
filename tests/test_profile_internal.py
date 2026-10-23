import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.profile_client import get_profile, get_profiles_batch
from Model.profile_db import DualWriteCursor, rewrite_profile_sql
from Model.profile_service import ProfileService
from services.catalog import owner_of


def test_internal_profile_paths_belong_to_profile():
    assert owner_of("/netwirkProfileRoute/internal/get_profile") == "profile"
    assert owner_of("/netwirkProfileRoute/internal/get_profiles_batch") == "profile"


def test_profile_internal_key_rejects_wrong_header(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    service = ProfileService.__new__(ProfileService)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Internal-Key": "wrong"}):
        denied = service._require_internal_key()
    assert denied is not None
    body, status = denied
    assert status == 401
    assert body.get_json()["Status"] == "Failure"


def test_rewrite_profile_sql_leaves_registration_alone():
    sql = (
        "SELECT p.userId, r.fullName FROM icebreaker.profile p "
        "JOIN icebreaker.registration r ON p.userId = r.userId"
    )
    rewritten = rewrite_profile_sql(sql, "vyb_profile")
    assert "vyb_profile.profile" in rewritten
    assert "icebreaker.registration" in rewritten


def test_profile_dual_write_mirrors_updates():
    class Fake:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    fake = Fake()
    cursor = DualWriteCursor(fake, "vyb_profile")
    cursor.execute(
        "UPDATE icebreaker.profile SET height = %s WHERE userId = %s",
        (170, 9),
    )
    assert fake.calls[0][0] == "UPDATE vyb_profile.profile SET height = %s WHERE userId = %s"
    assert fake.calls[1][0] == "UPDATE icebreaker.profile SET height = %s WHERE userId = %s"


def test_profile_client_posts_to_profile_service(monkeypatch):
    monkeypatch.setenv("PROFILE_SERVICE_URL", "http://profile:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": "Success", "profile": {"userId": 7}}

    with patch("Model.profile_client.requests.post", return_value=FakeResponse()) as post:
        body = get_profile(7)
    assert body["profile"]["userId"] == 7
    assert post.call_args[0][0] == "http://profile:8000/netwirkProfileRoute/internal/get_profile"


def test_profile_client_batch_empty_list():
    assert get_profiles_batch([]) == []


def test_profile_json_safe_bytes():
    service = ProfileService.__new__(ProfileService)
    assert service._json_safe(b"hello") == "hello"
    assert service._json_safe(None) is None
