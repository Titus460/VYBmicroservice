import os

from flask import Blueprint, jsonify, redirect, request, send_from_directory

from Model.recsys.demo_explain import enrich_demo_learning, enrich_demo_matches, enrich_demo_my_checkins
from Model.recsys.llm_explain import is_ai_explain_enabled

matchDemoRoute = Blueprint("matchDemoRoute", __name__)

_DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))


@matchDemoRoute.route("/demo/match")
@matchDemoRoute.route("/demo.html")
def match_demo_page():
    return send_from_directory(_DOCS_DIR, "match-demo.html")


@matchDemoRoute.route("/demo")
def match_demo_redirect():
    return redirect("/demo/match")


@matchDemoRoute.route("/api/demo/match-explain/status", methods=["GET"])
def match_explain_status():
    return jsonify({"groq": is_ai_explain_enabled()})


@matchDemoRoute.route("/api/demo/match-explain", methods=["POST"])
def match_explain():
    body = request.get_json(silent=True) or {}
    user = body.get("user")
    matches = body.get("matches") or []
    learned = body.get("learned")
    for_you_only = body.get("for_you_only", True)

    if not user or not isinstance(matches, list):
        return jsonify({"ok": False, "error": "Expected user and matches[]"}), 400

    result = enrich_demo_matches(user, matches, learned=learned, for_you_only=for_you_only)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@matchDemoRoute.route("/api/demo/learn-explain", methods=["POST"])
def learn_explain():
    body = request.get_json(silent=True) or {}
    user = body.get("user")
    sections = body.get("sections") or []
    stats = body.get("stats")

    if not user or not isinstance(sections, list):
        return jsonify({"ok": False, "error": "Expected user and sections[]"}), 400

    result = enrich_demo_learning(user, sections, stats=stats)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@matchDemoRoute.route("/api/demo/my-checkins-explain", methods=["POST"])
def my_checkins_explain():
    body = request.get_json(silent=True) or {}
    user = body.get("user")

    if not user:
        return jsonify({"ok": False, "error": "Expected user"}), 400

    result = enrich_demo_my_checkins(user)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status
