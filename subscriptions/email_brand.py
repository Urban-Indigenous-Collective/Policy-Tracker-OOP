"""Email-safe brand tokens mirrored from frontend/lib/design/tokens.css.

Keep in sync when brand colors change. Email clients need inline hex, not CSS variables.
"""

from __future__ import annotations

# ——— Color: brand (tokens.css @theme) ———
BACKGROUND = "#000000"
FOREGROUND = "#ffffff"
ACCENT = "#3fbfa7"
ACCENT_BRIGHT = "#5ecdb9"
MUTED = "#a3a3a3"
SURFACE_BORDER = "#1a1a1a"  # approx white/10 on black for solid borders in email

FONT_STACK = (
    "Montserrat, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "Helvetica, Arial, sans-serif"
)
MONO_STACK = "'Roboto Mono', ui-monospace, Menlo, Consolas, monospace"

SITE_NAME = "MMIP Policy Tracker"
ORG_NAME = "Urban Indigenous Collective"
DEFAULT_PUBLIC_ORIGIN = "https://policy.urbanindigenouscollective.org"
# Cropped flush asset for email (source logo has large transparent padding).
LOGO_PATH = "/brand/uic-logo-email.png"
LOGO_ALT = "Urban Indigenous Collective"
# Match pre-cleanup visual size (artwork height inside the old 120px box).
LOGO_HEIGHT_PX = 72
# Full logo tight-crop aspect ~911×1231 (includes arched wordmark).
LOGO_WIDTH_PX = 53
# Breathing room that used to come from transparent canvas (~24px at 120px box).
LOGO_PAD_TOP_PX = 60
LOGO_PAD_BOTTOM_PX = 24
