import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.social_client import get_connection, get_social
from Model.social_db import DualWriteCursor, rewrite_social_sql
from Model.social_service import SocialService
from services.catalog import owner_of


def test_internal_social_paths_belong_to_social():
    assert owner_of("/netwirkProfileRoute/internal/get_social") == "social"
    assert owner_of("/netwirkProfileRoute/internal/get_connection") == "social"


def test_social_internal_key_rejects_wrong_header(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    service = SocialService.__new__(SocialService)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Internal-Key": "wrong"}):
        denied = service._require_internal_key()
    assert denied is not None
    body, status = denied
    assert status == 401


def test_rewrite_social_sql_leaves_profile_alone():
    sql = (
        "SELECT b.blockedId, p.profilePic FROM icebreaker.blockedUsers b "
        "JOIN icebreaker.profile p ON b.blockedId = p.userId"
    )
    rewritten = rewrite_social_sql(sql, "vyb_social")
    assert "vyb_social.blockedUsers" in rewritten
    assert "icebreaker.profile" in rewritten


def test_social_dual_write_mirrors_updates():
    class Fake:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    fake = Fake()
    cursor = DualWriteCursor(fake, "vyb_social")
    cursor.execute(
        "INSERT INTO icebreaker.blockedUsers (userId, blockedId) VALUES (%s, %s)",
        (1, 2),
    )
    assert "vyb_social.blockedUsers" in fake.calls[0][0]
    assert "icebreaker.blockedUsers" in fake.calls[1][0]


def test_social_client_posts_to_social_service(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "profile")
    monkeypatch.setenv("SOCIAL_SERVICE_URL", "http://social:8000")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": "Success", "userId": 7, "blockedIds": []}

    with patch("Model.social_client.requests.post", return_value=FakeResponse()) as post:
        body = get_social(7)
    assert body["userId"] == 7
    assert post.call_args[0][0] == "http://social:8000/netwirkProfileRoute/internal/get_social"
    assert get_connection  # imported for catalog-style coverage
