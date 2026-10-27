"""Shared extension instances.

Kept in their own module so models and blueprints can import them without
creating circular imports through the app factory.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
