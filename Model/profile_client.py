"""HTTP client for other services to read profile-owned data.

Other modules should call this instead of SELECT/JOIN icebreaker.profile.
"""

import os

import requests

DEFAULT_PROFILE_URL = "http://profile:8000"
TIMEOUT_SECONDS = 5


def _profile_base_url():
    return os.getenv("PROFILE_SERVICE_URL", DEFAULT_PROFILE_URL).rstrip("/")


def _headers():
    headers = {"Content-Type": "application/json"}
    key = os.getenv("INTERNAL_API_KEY", "").strip()
    if key:
        headers["X-Internal-Key"] = key
    return headers


def get_profile(user_id):
    response = requests.post(
        f"{_profile_base_url()}/netwirkProfileRoute/internal/get_profile",
        json={"userId": user_id},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return None
    return body


def get_profiles_batch(user_ids):
    if not user_ids:
        return []
    response = requests.post(
        f"{_profile_base_url()}/netwirkProfileRoute/internal/get_profiles_batch",
        json={"userIds": list(user_ids)},
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("Status") != "Success":
        return []
    return body.get("profiles") or []
