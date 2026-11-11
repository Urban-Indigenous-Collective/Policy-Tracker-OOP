"""Design-system email template smoke tests."""

from __future__ import annotations

from subscriptions.email_brand import ACCENT, SITE_NAME
from subscriptions.templates import (
    render_digest_email,
    render_manage_otp_email,
    render_welcome_email,
)

_CONFIDENTIALITY_MARKERS = (
    "CONFIDENTIALITY NOTICE",
    "privileged, confidential",
    "intended recipient",
    "strictly prohibited",
)


def test_welcome_email_uses_brand_tokens():
    subject, html = render_welcome_email(state_label="Washington")
    assert "Washington" in subject
    assert SITE_NAME in subject
    assert ACCENT in html
    assert "You're subscribed" in html
    assert "#000000" in html
    assert "/brand/uic-logo-email.png" in html


def test_otp_email_includes_code_and_magic_link():
    subject, html = render_manage_otp_email(
        code="123456",
        state_label="Oregon",
        manage_url="https://policy.urbanindigenouscollective.org/subscribe/manage?token=abc",
    )
    assert "Manage" in subject or "manage" in subject.lower()
    assert "123456" in html
    assert "Oregon" in html
    assert "/subscribe/manage?token=abc" in html
    assert "Manage subscriptions" in html


def test_email_shell_omits_confidentiality_notice():
    templates = [
        render_welcome_email(state_label="Washington")[1],
        render_manage_otp_email(code="123456", state_label="Oregon")[1],
        render_digest_email(state_labels=["WA"], items=[])[1],
    ]
    for html in templates:
        upper = html.upper()
        for marker in _CONFIDENTIALITY_MARKERS:
            assert marker.upper() not in upper, marker


def test_digest_email_lists_items():
    subject, html = render_digest_email(
        state_labels=["WA", "OR"],
        items=[
            {
                "title": "Example Act",
                "url": "https://policy.urbanindigenouscollective.org/states/WA/bills/x",
                "state": "WA",
                "summary": "Short summary",
            }
        ],
    )
    assert "Policy updates" in subject
    assert "Example Act" in html
    assert "Short summary" in html
    assert "WA" in html
