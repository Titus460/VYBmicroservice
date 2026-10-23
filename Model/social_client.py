"""HTTP client for other services to read social-owned data.

Local monolith (`app.py`) calls SocialService in-process.
"""

import os

import requests

from Model.internal_rpc import should_http

DEFAULT_SOCIAL_URL = "http://social:8000"
TIMEOUT_SECONDS = 5


def _social_base_url():
    return os.getenv("SOCIAL_SERVICE_URL", DEFAULT_SOCIAL_URL).rstrip("/")


def _headers():
    headers = {"Content-Type": "application/json"}
    key = os.getenv("INTERNAL_API_KEY", "").strip()
    if key:
        headers["X-Internal-Key"] = key
    return headers


def _lookup_social_local(user_id):
    from Model.social_service import SocialService

    return SocialService().lookup_social(user_id)


def _lookup_connection_local(user_id, other_user_id):
    from Model.social_service import SocialService

    return SocialService().lookup_connection(user_id, other_user_id)


def get_social(user_id):
    if not should_http(_social_base_url()):
        return _lookup_social_local(user_id)
    response = requests.post(
        f"{_social_base_url()}/netwirkProfileRoute/internal/get_social",
        json={"userId": user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body


def get_connection(user_id, other_user_id):
    if not should_http(_social_base_url()):
        return _lookup_connection_local(user_id, other_user_id)
    response = requests.post(
        f"{_social_base_url()}/netwirkProfileRoute/internal/get_connection",
        json={"userId": user_id, "otherUserId": other_user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body
