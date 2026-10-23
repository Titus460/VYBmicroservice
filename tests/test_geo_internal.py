import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.geo_client import get_incognito, get_location, get_locations_batch
from Model.geo_db import DualWriteCursor, rewrite_geo_sql
from Model.geo_service import GeoService
from services.catalog import owner_of


def test_internal_geo_paths_belong_to_geo():
    assert owner_of("/netwirkProfileRoute/internal/get_incognito") == "geo"
    assert owner_of("/netwirkProfileRoute/internal/get_location") == "geo"
    assert owner_of("/netwirkProfileRoute/internal/get_locations_batch") == "geo"


def test_geo_internal_key_rejects_wrong_header(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    service = GeoService.__new__(GeoService)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-Internal-Key": "wrong"}):
        denied = service._require_internal_key()
    assert denied is not None
    body, status = denied
    assert status == 401
    assert body.get_json()["Status"] == "Failure"


def test_rewrite_geo_sql_leaves_registration_alone():
    sql = (
        "SELECT l.userId, r.fullName FROM icebreaker.location l "
        "JOIN icebreaker.registration r ON l.userId = r.userId"
    )
    rewritten = rewrite_geo_sql(sql, "vyb_geo")
    assert "vyb_geo.location" in rewritten
    assert "icebreaker.registration" in rewritten


def test_geo_dual_write_mirrors_updates():
    class Fake:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    fake = Fake()
    cursor = DualWriteCursor(fake, "vyb_geo")
    cursor.execute(
        "UPDATE icebreaker.location SET incognito = %s WHERE userId = %s",
        (1, 9),
    )
    assert fake.calls[0][0] == "UPDATE vyb_geo.location SET incognito = %s WHERE userId = %s"
    assert fake.calls[1][0] == "UPDATE icebreaker.location SET incognito = %s WHERE userId = %s"


def test_geo_client_posts_to_geo_service(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "profile")
    monkeypatch.setenv("GEO_SERVICE_URL", "http://geo:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": "Success", "incognito": False}

    with patch("Model.geo_client.requests.post", return_value=FakeResponse()) as post:
        body = get_incognito(7)
    assert body["incognito"] is False
    assert post.call_args[0][0] == "http://geo:8000/netwirkProfileRoute/internal/get_incognito"
    assert post.call_args[1]["json"] == {"userId": 7}
    assert post.call_args[1]["headers"]["X-Internal-Key"] == "secret"


def test_geo_client_location_and_batch_empty(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "recsys")
    monkeypatch.setenv("GEO_SERVICE_URL", "http://geo:8000")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"Status": "Success", "location": {"userId": 7}}

    with patch("Model.geo_client.requests.post", return_value=FakeResponse()) as post:
        body = get_location(7)
    assert body["location"]["userId"] == 7
    assert post.call_args[0][0] == "http://geo:8000/netwirkProfileRoute/internal/get_location"
    assert get_locations_batch([]) == []
