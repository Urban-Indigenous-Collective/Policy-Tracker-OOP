"""State update subscriptions (env-gated email OTP + local store)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def register_subscriptions_api(app: "Flask") -> None:
    from subscriptions.routes import register_subscriptions_api as _register

    _register(app)


__all__ = ["register_subscriptions_api"]
