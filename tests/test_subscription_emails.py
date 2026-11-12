"""Design-system email template smoke tests."""

from __future__ import annotations

import base64
from email import message_from_bytes

from subscriptions.email_brand import (
    ACCENT,
    DEFAULT_PUBLIC_ORIGIN,
    LOGO_CID,
    LOGO_CID_SRC,
    LOGO_PATH,
    SITE_NAME,
    STATUS_FAILED,
    STATUS_NEUTRAL,
    STATUS_PASSED,
    STATUS_PENDING,
)
from subscriptions.mail import _build_raw_mime, _email_logo_path
from subscriptions.templates import (
    render_digest_email,
    render_manage_otp_email,
    render_monthly_digest_email,
    render_welcome_email,
)
from subscriptions.templates.render import bill_status_variant, _logo_img_src

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
    assert LOGO_PATH in html
    assert DEFAULT_PUBLIC_ORIGIN in html


def test_email_shell_forces_black_background_for_apple_mail():
    """Apple Mail remaps CSS-only backgrounds; shell must use bgcolor + light-only."""
    _, html = render_welcome_email(state_label="Washington")
    assert 'name="color-scheme" content="light only"' in html
    assert 'name="supported-color-schemes" content="light only"' in html
    assert 'bgcolor="#000000"' in html
    assert "background-color:#000000" in html


def test_welcome_email_includes_manage_magic_link():
    _, html = render_welcome_email(
        state_label="Washington",
        manage_url="https://policy.urbanindigenouscollective.org/subscribe/manage?token=abc",
    )
    assert "Manage or unsubscribe" in html
    assert "/subscribe/manage?token=abc" in html
    assert f'color:{ACCENT}' in html
    assert "Manage or unsubscribe" in html.split("Urban Indigenous Collective")[-1]


def test_email_logo_ignores_localhost_public_origin():
    """Magic-link origin may be localhost; logo assets must stay publicly reachable."""
    assert _logo_img_src(asset_origin=None) == f"{DEFAULT_PUBLIC_ORIGIN}{LOGO_PATH}"
    _, html = render_digest_email(
        state_labels=["NC"],
        items=[],
        public_origin="http://127.0.0.1:3000",
    )
    assert "127.0.0.1:3000/brand/" not in html
    assert f"{DEFAULT_PUBLIC_ORIGIN}{LOGO_PATH}" in html
    assert "http://127.0.0.1:3000" in html  # footer/site link may still be local


def test_email_logo_supports_cid_src():
    _, html = render_digest_email(
        state_labels=["NC"],
        items=[],
        logo_src=LOGO_CID_SRC,
    )
    assert f'src="{LOGO_CID_SRC}"' in html
    assert LOGO_PATH not in html


def test_gmail_mime_inlines_logo_as_cid():
    assert _email_logo_path().is_file()
    _, html = render_digest_email(
        state_labels=["NC"],
        items=[{"title": "Savanna's Act companion", "url": "https://example.com", "state": "NC"}],
        logo_src=LOGO_CID_SRC,
    )
    raw = _build_raw_mime(
        sender="info@urbanindigenouscollective.org",
        to="reader@example.com",
        subject="Policy updates",
        html=html,
    )
    pad = "=" * (-len(raw) % 4)
    msg = message_from_bytes(base64.urlsafe_b64decode(raw + pad))
    assert msg.get_content_type() == "multipart/related"
    cids = []
    for part in msg.walk():
        if part.get_content_type() == "image/png":
            cids.append(part.get("Content-ID"))
    assert f"<{LOGO_CID}>" in cids


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
    assert "Manage or unsubscribe" in html


def test_email_shell_omits_confidentiality_notice():
    templates = [
        render_welcome_email(state_label="Washington")[1],
        render_manage_otp_email(code="123456", state_label="Oregon")[1],
        render_digest_email(state_labels=["WA"], items=[])[1],
        render_monthly_digest_email(
            period_label="November 2026",
            overview="Quiet month.",
            items=[],
        )[1],
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
        manage_url="https://policy.urbanindigenouscollective.org/subscribe/manage?token=dig",
    )
    assert "Policy updates" in subject
    assert "Example Act" in html
    assert "Short summary" in html
    assert "New or changed policies for Washington, Oregon." in html
    assert "Washington" in html
    assert ">WA<" not in html
    assert "Manage or unsubscribe" in html
    assert "/subscribe/manage?token=dig" in html


def test_digest_email_spells_out_state_codes_and_keeps_national():
    _, html = render_digest_email(
        state_labels=["NC", "National"],
        items=[
            {
                "title": "NC Bill",
                "url": "https://example.com/nc",
                "state": "NC",
            },
            {
                "title": "Federal Bill",
                "url": "https://example.com/nat",
                "state": "National",
            },
        ],
    )
    assert "New or changed policies for North Carolina, National." in html
    assert "North Carolina" in html
    assert "National" in html
    assert ">NC<" not in html


def test_bill_status_variant_matches_frontend_rules():
    assert bill_status_variant(status="Passed") == "passed"
    assert bill_status_variant(status="Failed") == "failed"
    assert bill_status_variant(status="Pending") == "pending"
    assert bill_status_variant(status="", progression="Signed by Governor") == "passed"
    assert bill_status_variant(status="", progression="Vetoed") == "failed"
    assert bill_status_variant(status="", progression="In Committee") == "pending"
    assert bill_status_variant(status="Unknown", progression="") == "neutral"


def test_digest_email_status_pills_use_token_colors():
    _, html = render_digest_email(
        state_labels=["WA"],
        items=[
            {
                "title": "Passed Bill",
                "url": "https://example.com/p",
                "state": "WA",
                "status": "Passed",
                "summary": "Status: Pending → Passed",
            },
            {
                "title": "Pending Bill",
                "url": "https://example.com/q",
                "state": "OR",
                "status": "Pending",
                "progression": "Introduced",
            },
            {
                "title": "Failed Bill",
                "url": "https://example.com/r",
                "state": "NC",
                "status": "Failed",
            },
            {
                "title": "New Bill",
                "url": "https://example.com/s",
                "state": "CA",
                "kind": "new_live",
                "summary": "New on the tracker",
            },
        ],
    )
    assert "PASSED" in html
    assert "PENDING" in html
    assert "INTRODUCED" in html
    assert "FAILED" in html
    assert "NEW" in html
    assert f"border:1px solid {STATUS_PASSED}" in html
    assert f"color:{STATUS_PASSED}" in html
    assert f"border:1px solid {STATUS_PENDING}" in html
    assert f"border:1px solid {STATUS_FAILED}" in html
    # Outline pills stay readable on the black email shell
    assert "#000000" in html
    assert STATUS_FAILED == STATUS_PENDING  # mirrors tokens.css
    assert STATUS_NEUTRAL == "#a3a3a3"


def test_monthly_digest_email_includes_overview_and_period():
    subject, html = render_monthly_digest_email(
        period_label="November 2026",
        overview=(
            "Activity concentrated in North Carolina and National.\n\n"
            "Two new bills were added; one status moved to Passed."
        ),
        items=[
            {
                "title": "Example Act",
                "url": "https://policy.urbanindigenouscollective.org/states/WA/bills/x",
                "state": "WA",
                "status": "Pending",
                "summary": "Short summary",
            }
        ],
        manage_url="https://policy.urbanindigenouscollective.org/subscribe/manage?token=abc",
    )
    assert subject == f"Monthly digest — November 2026 — {SITE_NAME}"
    assert "Monthly digest" in html
    assert "November 2026" in html
    assert "This month at a glance" in html
    assert "Activity concentrated in North Carolina and National." in html
    assert "Updates this month" in html
    assert "Example Act" in html
    assert "Short summary" in html
    assert "Washington" in html
    assert "Manage or unsubscribe" in html
    assert "/subscribe/manage?token=abc" in html
    assert ACCENT in html
    assert "Manage or unsubscribe" in html.split("Urban Indigenous Collective")[-1]


def test_monthly_digest_email_empty_items_copy():
    _, html = render_monthly_digest_email(
        period_label="October 2026",
        overview="",
        items=[],
    )
    assert "No new policies in this period." in html
    assert "quiet month" in html.lower()
