"""Decide whether service-to-service calls go over HTTP or in-process.

Docker Compose sets SERVICE_NAME and uses hostnames like auth/social/geo.
Local `app.py` is a monolith: those hostnames do not resolve, and an HTTP
call back into the same Flask server would deadlock.
"""

import os
from urllib.parse import urlparse

_COMPOSE_HOSTS = frozenset({"auth", "social", "geo", "profile", "recsys", "legacy"})


def in_compose():
    return bool(os.getenv("SERVICE_NAME")) or os.path.exists("/.dockerenv")


def should_http(service_url):
    flag = os.getenv("INTERNAL_API_INPROCESS", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return False
    if in_compose():
        return True
    host = (urlparse(service_url or "").hostname or "").lower()
    return bool(host) and host not in _COMPOSE_HOSTS
