"""HTTP client for other services to read profile-owned data.

Other modules should call this instead of SELECT/JOIN icebreaker.profile.
Local monolith (`app.py`) calls ProfileService in-process.
"""

import os

import requests

from Model.internal_rpc import should_http

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


def _profile_service():
    from Model.profile_service import ProfileService

    return ProfileService()


def get_profile(user_id):
    if not should_http(_profile_base_url()):
        service = _profile_service()
        cursor = service.db.cur()
        try:
            cursor.execute(
                "SELECT * FROM icebreaker.profile WHERE userId = %s",
                (int(user_id),),
            )
            profile_row = service._row_to_profile(cursor, cursor.fetchone())
            cursor.execute(
                "SELECT loginUserId, picture_urls, IsProfilePicture FROM icebreaker.userPictures WHERE loginUserId = %s",
                (int(user_id),),
            )
            pictures = [
                {
                    "loginUserId": service._json_safe(r[0]),
                    "picture_urls": service._json_safe(r[1]),
                    "IsProfilePicture": service._json_safe(r[2]),
                }
                for r in cursor.fetchall()
            ]
        finally:
            cursor.close()
        if not profile_row:
            return None
        return {"Status": "Success", "profile": profile_row, "pictures": pictures}
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
    if not should_http(_profile_base_url()):
        service = _profile_service()
        ids = [int(uid) for uid in user_ids]
        cursor = service.db.cur()
        try:
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"SELECT * FROM icebreaker.profile WHERE userId IN ({placeholders})",
                tuple(ids),
            )
            return [service._row_to_profile(cursor, row) for row in cursor.fetchall()]
        finally:
            cursor.close()
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
