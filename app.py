import logging
import os
import secrets
import sys
from logging import FileHandler


def _load_dotenv():
    """Load .env from project root for local development (optional)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

LOG_FILE = "app_startup_error.log"
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
    format="%(asctime)s [%(levelname)s] %(message)s",
)

try:
    from datetime import timedelta

    from flask import Flask, jsonify, request, Response
    from flask_cors import CORS
    from flask_jwt_extended import JWTManager
    from flasgger import LazyJSONEncoder, Swagger
    from metrics import metrics_response

    from App.matchDemoRoute import matchDemoRoute
    from App.netwirkProfileRoute import netwirkProfileRoute
    from App.netwirk_registrationRoute import registrationRoute

    app = Flask(__name__)
    try:
        # Flask 3 + newer flasgger
        app.json = LazyJSONEncoder(app)
    except TypeError:
        # EC2 / older stack (worked before cleanup)
        app.json_encoder = LazyJSONEncoder
    CORS(app)

    _swagger_auth_enabled = os.getenv("SWAGGER_AUTH_ENABLED", "false").lower() == "true"
    _swagger_username = os.getenv("SWAGGER_AUTH_USERNAME", "")
    _swagger_password = os.getenv("SWAGGER_AUTH_PASSWORD", "")
    _swagger_paths = ("/swagger", "/docs", "/openapi.json", "/apispec_1.json")

    def _swagger_auth_required(path):
        return any(path == route or path.startswith(route + "/") for route in _swagger_paths)

    @app.before_request
    def protect_api_documentation():
        if not _swagger_auth_enabled or not _swagger_auth_required(request.path):
            return None

        auth = request.authorization
        valid = (
            auth is not None
            and secrets.compare_digest(auth.username or "", _swagger_username)
            and secrets.compare_digest(auth.password or "", _swagger_password)
        )
        if valid:
            return None

        return Response(
            "Swagger authentication required", 401,
            {"WWW-Authenticate": 'Basic realm="Swagger"'},
        )

    app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=120)
    JWTManager(app)

    app.register_blueprint(registrationRoute)
    app.register_blueprint(netwirkProfileRoute)
    app.register_blueprint(matchDemoRoute)

    app.config["SWAGGER"] = {
        "title": "Icebreaker API",
        "termsOfService": "",
        "uiversion": 3,
        "version": "0.0.1",
        "specs_route": "/swagger",
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
            }
        },
    }

    Swagger(app)

    @app.route("/")
    def hello_world():
        return jsonify(
            {
                "status": "ok",
                "swagger": "/swagger",
                "demo": "/demo/match",
                "offline_feed_dashboard": "/offline-feed-dashboard",
            }
        )

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/offline-feed-dashboard")
    def offline_feed_dashboard():
        """Local HTML dashboard for offline feed ranking (in-memory)."""
        from Model.recsys.offline_feed_dashboard import render_dashboard_html

        limit = int(request.args.get("limit", 100))
        return Response(render_dashboard_html(limit=limit), mimetype="text/html")

    @app.route("/offline-feed-dashboard.json")
    def offline_feed_dashboard_json():
        from Model.recsys.offline_feed_dashboard import (
            dashboard_summary,
            list_offline_feed_events,
        )

        limit = int(request.args.get("limit", 100))
        events = list_offline_feed_events(limit=limit)
        return jsonify({"summary": dashboard_summary(events), "events": events})

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

except Exception:
    logging.exception("Error during app startup/imports")
    sys.exit(1)
