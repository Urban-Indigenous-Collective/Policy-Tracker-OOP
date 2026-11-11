"""Build inline-styled HTML emails from UIC brand tokens."""

from __future__ import annotations

import html
from typing import Sequence

from subscriptions.email_brand import (
    ACCENT,
    BACKGROUND,
    DEFAULT_PUBLIC_ORIGIN,
    FONT_STACK,
    FOREGROUND,
    LOGO_ALT,
    LOGO_HEIGHT_PX,
    LOGO_PAD_BOTTOM_PX,
    LOGO_PAD_TOP_PX,
    LOGO_PATH,
    LOGO_WIDTH_PX,
    MONO_STACK,
    MUTED,
    ORG_NAME,
    SITE_NAME,
    SURFACE_BORDER,
)


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _shell(*, title: str, preheader: str, body_html: str, public_origin: str) -> str:
    origin = (public_origin or DEFAULT_PUBLIC_ORIGIN).rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:{BACKGROUND};color:{FOREGROUND};font-family:{FONT_STACK};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {_esc(preheader)}
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background:{BACKGROUND};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
               style="max-width:560px;border:1px solid {SURFACE_BORDER};">
          <tr>
            <td style="height:3px;background:{ACCENT};font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td align="left" style="padding:{LOGO_PAD_TOP_PX}px 28px {LOGO_PAD_BOTTOM_PX}px 28px;text-align:left;">
              <img src="{_esc(origin + LOGO_PATH)}"
                   width="{LOGO_WIDTH_PX}"
                   height="{LOGO_HEIGHT_PX}"
                   alt="{_esc(LOGO_ALT)}"
                   style="display:block;margin:0;padding:0;width:{LOGO_WIDTH_PX}px;height:auto;border:0;outline:none;text-decoration:none;" />
            </td>
          </tr>
          <tr>
            <td align="left" style="padding:0 28px 8px;font-family:{MONO_STACK};font-size:12px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;color:{ACCENT};text-align:left;">
              {_esc(SITE_NAME)}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 28px;font-family:{FONT_STACK};font-size:15px;line-height:1.6;color:{FOREGROUND};">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 28px;font-family:{FONT_STACK};font-size:12px;line-height:1.5;color:{MUTED};border-top:1px solid {SURFACE_BORDER};padding-top:20px;">
              {_esc(ORG_NAME)} ·
              <a href="{_esc(origin)}" style="color:{ACCENT};text-decoration:none;">{_esc(origin)}</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def render_welcome_email(
    *,
    state_label: str,
    manage_url: str | None = None,
    public_origin: str | None = None,
) -> tuple[str, str]:
    """Return (subject, html) for a new state subscription."""
    origin = public_origin or DEFAULT_PUBLIC_ORIGIN
    subject = f"Subscribed to {state_label} updates — {SITE_NAME}"
    manage_block = ""
    if manage_url:
        manage_block = f"""
        <p style="margin:20px 0 0;">
          <a href="{_esc(manage_url)}"
             style="display:inline-block;padding:12px 20px;border:1px solid {FOREGROUND};color:{FOREGROUND};text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">
            Manage subscriptions
          </a>
        </p>
        """
    else:
        manage_block = f"""
        <p style="margin:16px 0 0;color:{MUTED};font-size:13px;">
          To change or cancel later, use the bell on the policy map or list and verify this email.
        </p>
        """
    body = f"""
      <p style="margin:0 0 12px;font-family:{MONO_STACK};font-size:22px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
        You're subscribed
      </p>
      <p style="margin:0;">
        You'll get updates when we publish new or changed MMIP-related policies for
        <strong style="color:{ACCENT};">{_esc(state_label)}</strong>.
      </p>
      {manage_block}
    """
    return subject, _shell(
        title=subject,
        preheader=f"You're subscribed to {state_label} policy updates.",
        body_html=body,
        public_origin=origin,
    )


def render_manage_otp_email(
    *,
    code: str,
    state_label: str,
    manage_url: str | None = None,
    public_origin: str | None = None,
) -> tuple[str, str]:
    """Return (subject, html) for manage verification (OTP + optional magic link)."""
    origin = public_origin or DEFAULT_PUBLIC_ORIGIN
    subject = f"Manage your subscriptions — {SITE_NAME}"
    link_block = ""
    if manage_url:
        link_block = f"""
      <p style="margin:24px 0 12px;color:{MUTED};font-size:13px;">Or open this one-time link:</p>
      <p style="margin:0;">
        <a href="{_esc(manage_url)}"
           style="display:inline-block;padding:12px 20px;border:1px solid {FOREGROUND};color:{FOREGROUND};text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">
          Manage subscriptions
        </a>
      </p>
        """
    body = f"""
      <p style="margin:0 0 12px;font-family:{MONO_STACK};font-size:22px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
        Verify your email
      </p>
      <p style="margin:0 0 16px;">
        Enter this code in the policy tracker
        {f' (from {_esc(state_label)})' if state_label else ''} to manage or unsubscribe:
      </p>
      <p style="margin:0;font-family:{MONO_STACK};font-size:28px;font-weight:700;letter-spacing:0.35em;color:{ACCENT};">
        {_esc(code)}
      </p>
      {link_block}
      <p style="margin:16px 0 0;color:{MUTED};font-size:13px;">
        The code and link expire soon. If you didn't request this, you can ignore this email.
      </p>
    """
    return subject, _shell(
        title=subject,
        preheader=f"Your {SITE_NAME} verification code and manage link",
        body_html=body,
        public_origin=origin,
    )


def render_digest_email(
    *,
    state_labels: Sequence[str],
    items: Sequence[dict[str, str]],
    public_origin: str | None = None,
) -> tuple[str, str]:
    """Return (subject, html) for a state-updates digest (Phase 3 content shape).

    Each item: ``{title, url, state, summary?}``.
    """
    origin = public_origin or DEFAULT_PUBLIC_ORIGIN
    labels = ", ".join(state_labels) if state_labels else "your states"
    subject = f"Policy updates — {SITE_NAME}"
    if not items:
        rows = f'<p style="margin:0;color:{MUTED};">No new policies in this period.</p>'
    else:
        parts: list[str] = []
        for item in items:
            title = _esc(item.get("title") or "Policy update")
            url = _esc(item.get("url") or origin)
            state = _esc(item.get("state") or "")
            summary = _esc(item.get("summary") or "")
            summary_html = (
                f'<p style="margin:6px 0 0;color:{MUTED};font-size:13px;">{summary}</p>'
                if summary
                else ""
            )
            parts.append(
                f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid {SURFACE_BORDER};">
                <p style="margin:0;font-size:11px;letter-spacing:0.15em;text-transform:uppercase;color:{ACCENT};">{state}</p>
                <p style="margin:6px 0 0;">
                  <a href="{url}" style="color:{FOREGROUND};text-decoration:underline;">{title}</a>
                </p>
                {summary_html}
              </td>
            </tr>
                """
            )
        rows = (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">'
            + "".join(parts)
            + "</table>"
        )
    body = f"""
      <p style="margin:0 0 12px;font-family:{MONO_STACK};font-size:22px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
        Policy updates
      </p>
      <p style="margin:0 0 20px;color:{MUTED};font-size:13px;">
        New or changed policies for {_esc(labels)}.
      </p>
      {rows}
    """
    return subject, _shell(
        title=subject,
        preheader=f"Policy updates for {labels}",
        body_html=body,
        public_origin=origin,
    )
