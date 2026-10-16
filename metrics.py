"""Prometheus metrics for recommendation serving."""

from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST


recommendation_requests = Counter(
    "vibr_personalize_requests_total",
    "Recommendation requests handled by the application.",
)
recommendation_fallbacks = Counter(
    "vibr_personalize_fallback_total",
    "Recommendation requests served by the fallback ranker.",
)
cache_requests = Counter(
    "vibr_personalize_cache_requests_total",
    "Recommendation cache lookups.",
)
cache_hits = Counter(
    "vibr_personalize_cache_hits_total",
    "Recommendation cache hits.",
)
application_errors = Counter(
    "vibr_personalize_app_errors_total",
    "Recommendation responses that failed at application level.",
)


def record_recommendation_request():
    recommendation_requests.inc()


def record_fallback():
    recommendation_fallbacks.inc()


def record_application_error():
    application_errors.inc()


def metrics_response():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
