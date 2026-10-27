"""HomeLedger API.

Run locally:
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    flask --app run:app init-db   # optional, tables are created on boot
    python run.py
"""

from __future__ import annotations

import os

from flask import Flask, jsonify
from flask_cors import CORS

from .api import bp as api_bp
from .config import CONFIG_MAP
from .extensions import db


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    app.config.from_object(CONFIG_MAP.get(config_name, CONFIG_MAP["development"]))

    origins = app.config.get("CORS_ORIGINS", "*")
    CORS(
        app,
        resources={r"/api/*": {"origins": "*" if origins == "*" else origins.split(",")}},
        allow_headers=["Content-Type", "X-API-Key"],
    )

    db.init_app(app)
    app.register_blueprint(api_bp)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "addressProvider": app.config.get("ADDRESS_PROVIDER", "demo"),
                "addressLookupLive": app.config.get("ADDRESS_PROVIDER") == "os_places",
            }
        )

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"message": "Not found."}}), 404

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": {"message": "Document too large."}}), 413

    with app.app_context():
        # Fine for SQLite development. Use Flask-Migrate/Alembic for real
        # deployments so schema changes are reviewable.
        db.create_all()

    return app


__all__ = ["create_app"]
