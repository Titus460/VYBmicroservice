"""HTTP client for other services to read geo-owned location data.

Local monolith (`app.py`) calls GeoService in-process.
"""

import os

import requests

from Model.internal_rpc import should_http

DEFAULT_GEO_URL = "http://geo:8000"
TIMEOUT_SECONDS = 5


def _geo_base_url():
    return os.getenv("GEO_SERVICE_URL", DEFAULT_GEO_URL).rstrip("/")


def _headers():
    headers = {"Content-Type": "application/json"}
    key = os.getenv("INTERNAL_API_KEY", "").strip()
    if key:
        headers["X-Internal-Key"] = key
    return headers


def _lookup_incognito_local(user_id):
    from Model.geo_service import GeoService

    return GeoService().lookup_incognito(user_id)


def get_incognito(user_id):
    if not should_http(_geo_base_url()):
        return _lookup_incognito_local(user_id)
    response = requests.post(
        f"{_geo_base_url()}/netwirkProfileRoute/internal/get_incognito",
        json={"userId": user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body
