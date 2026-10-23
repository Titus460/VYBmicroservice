"""HTTP client for other services to read auth-owned user data.

Other modules should call this instead of SELECT/JOIN icebreaker.registration.
"""

import os

import requests

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


def get_user(user_id):
    response = requests.post(
        f"{_auth_base_url()}/registrationRoute/internal/get_user",
        json={"userId": user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body.get("user")


def get_users_batch(user_ids):
    if not user_ids:
        return []
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
