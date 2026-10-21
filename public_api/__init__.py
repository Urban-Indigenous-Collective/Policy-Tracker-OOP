"""Read-only public JSON API for the MMIP Policy Tracker frontend."""

from public_api.routes import public_api_bp


def register_public_api(app) -> None:
    app.register_blueprint(public_api_bp)
