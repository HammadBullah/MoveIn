"""Configuration, all from the environment.

Two rules for this service:

1. Secrets never leave the server. The address provider key lives here and only
   here; the Flutter app talks to this API, never to Ordnance Survey directly.
2. Every externally-sourced value is returned with its provenance, matching the
   ``Field`` model in the Flutter app.
"""

from __future__ import annotations

import os


class Config:
    # SQLite for local development, PostgreSQL in deployment:
    #   postgresql+psycopg://user:pass@host:5432/home_ledger
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///home_ledger.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Ordnance Survey Places (or another licensed address provider).
    # Access terms and pricing must be checked before commercial use.
    OS_PLACES_API_KEY = os.environ.get("OS_PLACES_API_KEY", "")
    OS_PLACES_URL = os.environ.get(
        "OS_PLACES_URL", "https://api.os.uk/search/places/v1/postcode"
    )
    ADDRESS_LOOKUP_TIMEOUT_SECONDS = float(
        os.environ.get("ADDRESS_LOOKUP_TIMEOUT_SECONDS", "6")
    )

    # "demo" returns the built-in sample catalogue; "os_places" is live.
    ADDRESS_PROVIDER = os.environ.get("ADDRESS_PROVIDER", "demo")

    # Document storage (S3-compatible or local). Files must be encrypted at
    # rest; the bucket should not be public.
    DOCUMENT_BUCKET = os.environ.get("DOCUMENT_BUCKET", "")
    DOCUMENT_STORAGE_MODE = os.environ.get("DOCUMENT_STORAGE_MODE", "local")

    MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

    # Comma-separated list of allowed origins for the web build.
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # PLACEHOLDER access control: a single shared key, so the scaffold is not
    # wide open by default. Replace with real authentication (and per-household
    # ownership checks) before this is exposed to anybody.
    API_KEY = os.environ.get("API_KEY", "dev-local-key")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "test": TestConfig,
    "production": Config,
}
