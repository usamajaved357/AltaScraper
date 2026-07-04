"""routes/ — HTTP routing only: blueprints map URLs to thin handlers, no business logic."""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Attach every route group (blueprint) to the Flask app.

    New route files added in later phases get one extra line here — this is the
    single place where the app learns about all of its URLs.
    """
    from .auth_routes import bp as auth_bp

    app.register_blueprint(auth_bp)
