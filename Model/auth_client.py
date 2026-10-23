"""HTTP client for other services to read auth-owned user data.

Other modules should call this instead of SELECT/JOIN icebreaker.registration.
Local monolith (`app.py`) calls AuthRegistrationService in-process.
"""

import os

import requests

from Model.internal_rpc import should_http

DEFAULT_AUTH_URL = "http://auth:8000"
TIMEOUT_SECONDS = 5


def _auth_base_url():
    return os.getenv("AUTH_SERVICE_URL", DEFAULT_AUTH_URL).rstrip("/")


def _headers():
    headers = {"Content-Type": "application/json"}
    key = os.getenv("INTERNAL_API_KEY", "").strip()
    if key:
        headers["X-Internal-Key"] = key
    return headers


def _lookup_user_local(user_id):
    from Model.auth_service import AuthRegistrationService

    return AuthRegistrationService().lookup_user(user_id)


def _lookup_users_local(user_ids):
    from Model.auth_service import AuthRegistrationService

    return AuthRegistrationService().lookup_users(user_ids)


def get_user(user_id):
    if not should_http(_auth_base_url()):
        return _lookup_user_local(user_id)
    response = requests.post(
        f"{_auth_base_url()}/registrationRoute/internal/get_user",
        json={"userId": user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body.get("user")


def get_users_batch(user_ids):
    if not user_ids:
        return []
    if not should_http(_auth_base_url()):
        return _lookup_users_local(user_ids)
    response = requests.post(
        f"{_auth_base_url()}/registrationRoute/internal/get_users_batch",
        json={"userIds": list(user_ids)},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return []
    return body.get("users") or []
