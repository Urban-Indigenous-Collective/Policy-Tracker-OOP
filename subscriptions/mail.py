"""Outbound mail for state subscriptions.

Providers:
- ``log`` (default): render HTML and write to the app log (local/dev).
- ``gmail``: send as ``info@`` via Gmail API + Workspace service account
  (same pattern as UIC-Core-Services membership).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Sequence

from subscriptions.email_brand import (
    DEFAULT_PUBLIC_ORIGIN,
    LOGO_CID,
    LOGO_CID_SRC,
    LOGO_PATH,
)
from subscriptions.templates import (
    render_digest_email,
    render_manage_otp_email,
    render_welcome_email,
)

logger = logging.getLogger(__name__)

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_GMAIL_SA_KEY_PATH = "~/.config/gmail-migration/service-account.json"
DEFAULT_GMAIL_FROM = (
    "Urban Indigenous Collective <info@urbanindigenouscollective.org>"
)

_token_cache: dict[str, tuple[str, float]] = {}


class MailDeliveryError(RuntimeError):
    """Raised when a real mail provider fails to deliver."""


def _public_origin() -> str:
    """Origin for magic links / site footer (may be localhost in local dev)."""
    return (
        os.getenv("NEXT_PUBLIC_SITE_URL")
        or os.getenv("PUBLIC_SITE_URL")
        or DEFAULT_PUBLIC_ORIGIN
    ).rstrip("/")


def _email_asset_origin() -> str:
    """Public origin for remote email img src only (never localhost site URL).

    Prod currently 404s ``/brand`` on Flask; Gmail sends prefer CID-inline instead.
    This origin is the HTTP fallback for log/preview renders.
    """
    return (
        os.getenv("STATE_SUBSCRIBE_EMAIL_ASSET_ORIGIN") or DEFAULT_PUBLIC_ORIGIN
    ).rstrip("/")


def _email_logo_path() -> Path:
    """Tracked email logo under frontend/public/brand."""
    return (
        Path(__file__).resolve().parent.parent
        / "frontend"
        / "public"
        / "brand"
        / Path(LOGO_PATH).name
    )


def _template_logo_kwargs() -> dict[str, str]:
    """Logo args for templates: CID when sending via Gmail, else asset origin."""
    kwargs: dict[str, str] = {"asset_origin": _email_asset_origin()}
    if _mail_provider() == "gmail":
        kwargs["logo_src"] = LOGO_CID_SRC
    return kwargs


def _mail_provider() -> str:
    return (os.getenv("STATE_SUBSCRIBE_MAIL_PROVIDER") or "log").strip().lower()


def _from_address() -> str:
    return (os.getenv("STATE_SUBSCRIBE_MAIL_FROM") or DEFAULT_GMAIL_FROM).strip()


def _gmail_sender_address() -> str:
    """Bare address used as Gmail API userId / JWT ``sub``."""
    raw = _from_address()
    if "<" in raw and ">" in raw:
        return raw.split("<", 1)[1].split(">", 1)[0].strip()
    return raw


def _load_gmail_sa_key() -> dict:
    inline = (os.getenv("STATE_SUBSCRIBE_GMAIL_SA_KEY") or "").strip()
    if inline:
        try:
            key = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise MailDeliveryError(
                "STATE_SUBSCRIBE_GMAIL_SA_KEY is not valid JSON"
            ) from exc
    else:
        path_raw = (
            os.getenv("STATE_SUBSCRIBE_GMAIL_SA_KEY_PATH") or DEFAULT_GMAIL_SA_KEY_PATH
        ).strip()
        path = Path(path_raw).expanduser()
        if not path.is_file():
            raise MailDeliveryError(
                f"Gmail service account key not found at {path}"
            )
        try:
            key = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MailDeliveryError(
                f"Could not read Gmail service account key at {path}"
            ) from exc

    if not key.get("client_email") or not key.get("private_key"):
        raise MailDeliveryError(
            "Gmail service account key missing client_email or private_key"
        )
    return key


def _gmail_access_token(key: dict, sender: str) -> str:
    cache_key = f"{key['client_email']}|{sender}"
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    try:
        import jwt
    except ImportError as exc:
        raise MailDeliveryError(
            "PyJWT is required for Gmail mail provider"
        ) from exc

    now = int(time.time())
    aud = key.get("token_uri") or GMAIL_TOKEN_URL
    assertion = jwt.encode(
        {
            "iss": key["client_email"],
            "sub": sender,
            "scope": GMAIL_SEND_SCOPE,
            "aud": aud,
            "iat": now,
            "exp": now + 3600,
        },
        key["private_key"],
        algorithm="RS256",
    )
    if isinstance(assertion, bytes):
        assertion = assertion.decode("ascii")

    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        aud,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MailDeliveryError(
            f"Google token exchange failed ({exc.code}): {detail}. "
            f"If unauthorized_client, add {GMAIL_SEND_SCOPE} to the service "
            f"account's domain-wide delegation."
        ) from exc
    except Exception as exc:
        raise MailDeliveryError(f"Google token exchange failed: {exc}") from exc

    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    if not token:
        raise MailDeliveryError("Google token response missing access_token")
    _token_cache[cache_key] = (token, time.time() + expires_in)
    return token


def _html_to_plain(html: str) -> str:
    # Lightweight fallback for multipart/alternative; not a full HTML parser.
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "MMIP Policy Tracker"


def _attach_inline_logo(msg: MIMEMultipart) -> None:
    """Attach the UIC email logo as an inline CID image (cid:logo)."""
    path = _email_logo_path()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise MailDeliveryError(f"Email logo not found at {path}") from exc
    img = MIMEImage(payload, _subtype="png")
    img.add_header("Content-ID", f"<{LOGO_CID}>")
    img.add_header("Content-Disposition", "inline", filename=path.name)
    msg.attach(img)


def _build_raw_mime(
    *,
    sender: str,
    to: str,
    subject: str,
    html: str,
    inline_logo: bool = True,
) -> str:
    if "\r" in to or "\n" in to:
        raise MailDeliveryError("Invalid recipient")
    from_header = (
        _from_address()
        if "<" in _from_address()
        else f"Urban Indigenous Collective <{sender}>"
    )
    use_cid = inline_logo and LOGO_CID_SRC in html
    if use_cid:
        msg: MIMEMultipart = MIMEMultipart("related")
        msg["From"] = from_header
        msg["To"] = to
        msg["Subject"] = subject
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(_html_to_plain(html), "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)
        _attach_inline_logo(msg)
    else:
        msg = MIMEMultipart("alternative")
        msg["From"] = from_header
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(_html_to_plain(html), "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
    return raw


def _send_via_gmail(*, to: str, subject: str, html: str) -> None:
    key = _load_gmail_sa_key()
    sender = _gmail_sender_address()
    token = _gmail_access_token(key, sender)
    raw = _build_raw_mime(sender=sender, to=to, subject=subject, html=html)
    url = (
        "https://gmail.googleapis.com/gmail/v1/users/"
        f"{urllib.parse.quote(sender)}/messages/send"
    )
    payload = json.dumps({"raw": raw}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            logger.info(
                "state_subscribe gmail status=%s to=%s from=%s",
                getattr(resp, "status", "?"),
                to,
                sender,
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MailDeliveryError(
            f"Gmail send failed ({exc.code}): {detail}"
        ) from exc
    except MailDeliveryError:
        raise
    except Exception as exc:
        raise MailDeliveryError(f"Gmail send failed: {exc}") from exc


def send_email(*, to: str, subject: str, html: str) -> None:
    """Deliver one HTML email via the configured provider (default: log only)."""
    provider = _mail_provider()
    if provider in ("", "log", "none", "stdout"):
        logger.info(
            "state_subscribe mail provider=log to=%s subject=%r html_bytes=%s",
            to,
            subject,
            len(html.encode("utf-8")),
        )
        if "letter-spacing:0.35em" in html or "verification code" in subject.lower():
            logger.info(
                "state_subscribe mail body logged "
                "(OTP emails — check prior template render)"
            )
        return

    if provider == "gmail":
        _send_via_gmail(to=to, subject=subject, html=html)
        return

    raise MailDeliveryError(
        f"Unknown STATE_SUBSCRIBE_MAIL_PROVIDER={provider!r}"
    )


def send_subscription_welcome(email: str, state: str) -> None:
    """Confirm a new signup with a welcome template."""
    manage_url = None
    subject, html = render_welcome_email(
        state_label=state,
        manage_url=manage_url,
        public_origin=_public_origin(),
        **_template_logo_kwargs(),
    )
    send_email(to=email, subject=subject, html=html)


def manage_link_url(magic_token: str) -> str:
    """Public URL for the one-time manage magic link."""
    from urllib.parse import quote

    return f"{_public_origin()}/subscribe/manage?token={quote(magic_token, safe='')}"


def send_subscription_code(
    email: str,
    code: str,
    state: str,
    *,
    magic_token: str | None = None,
) -> None:
    """Send verification code + optional magic link for managing subscriptions."""
    manage_url = manage_link_url(magic_token) if magic_token else None
    subject, html = render_manage_otp_email(
        code=code,
        state_label=state,
        manage_url=manage_url,
        public_origin=_public_origin(),
        **_template_logo_kwargs(),
    )
    # Always log plaintext OTP when provider is log — operators need it locally.
    if _mail_provider() in ("", "log", "none", "stdout"):
        logger.info(
            "state_subscribe OTP for %s (state=%s): %s",
            email,
            state,
            code,
        )
        if manage_url:
            logger.info("state_subscribe magic link for %s: %s", email, manage_url)
    send_email(to=email, subject=subject, html=html)


def send_subscription_digest(
    email: str,
    *,
    state_labels: Sequence[str],
    items: Sequence[dict[str, str]],
) -> None:
    """Send a digest email (Phase 3 entry point)."""
    subject, html = render_digest_email(
        state_labels=state_labels,
        items=items,
        public_origin=_public_origin(),
        **_template_logo_kwargs(),
    )
    send_email(to=email, subject=subject, html=html)
