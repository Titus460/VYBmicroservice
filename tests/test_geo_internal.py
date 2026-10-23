import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from Model.geo_client import get_incognito
from Model.geo_service import GeoService
from services.catalog import owner_of


def test_internal_incognito_path_belongs_to_geo():
    assert owner_of("/netwirkProfileRoute/internal/get_incognito") == "geo"


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


def test_geo_client_posts_to_geo_service(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "profile")
    monkeypatch.setenv("GEO_SERVICE_URL", "http://geo:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")

    class FakeResponse:
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
