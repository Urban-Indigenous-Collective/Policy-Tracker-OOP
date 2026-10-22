# Design tokens (UIC MMIP frontend)

Single source of truth for the reusable design system:

| Layer | Path | Use |
|--------|------|-----|
| **CSS / Tailwind** | [`lib/design/tokens.css`](../lib/design/tokens.css) | `@theme` utilities (`text-accent`, `px-content-inset`, `text-hero`, `text-status-pending`, …) and `@layer components` patterns (`uic-nav-link`, …) |
| **JS / SVG** | [`lib/design/tokens.ts`](../lib/design/tokens.ts) | Map stroke/fill, opacity — must stay in sync with `tokens.css` |

## Rules for new UI

1. **No raw hex or arbitrary `[NNpx]`** in components unless Figma needs a one-off; add a token first.
2. **Status / map colors** → `policyStatusColor` + `text-status-*` / `bg-status-*` utilities.
3. **Layout from Figma 160:2142** → spacing/size tokens (`nav-inset`, `content-inset`, `max-w-map`, …).
4. **Repeated typography** → `uic-*` component classes or `text-label-xs` + `tracking-label`.

### Figma 160:2142 reference values

| Element | Spec |
|--------|------|
| Intro body | Montserrat SemiBold **13px**, **24px** line-height (`leading-body-sm`) |
| Nav / donate / filters | Montserrat Bold **12px**, **3px** tracking (`tracking-label`) |
| Donate pill | `py-3.5` / `px-10`, `rounded-full`, `#3fbfa7`, white 12px label — see `DonateLink` |

## State drawer (Figma `161:3059`, search bar `239:6616`)

| Token | Value |
|--------|--------|
| `--width-state-drawer` | 508px (`w-state-drawer max-w-[100vw]`) |
| `--spacing-drawer-x` | 63px horizontal inset |
| Typography | `uic-drawer-state-title` (34px / bold mono), `uic-drawer-policies-count`, `uic-drawer-bill-id`, `uic-drawer-bill-body-regular` (18px / 28px leading) |
| Bill row | `--width-drawer-bill-row` 400px; id column 158px; title 239px |
| Chrome | `/ui/dismiss.svg`; status pill `--width/height-drawer-status-pill` |
| Site top bar | `--height-top-border` (3px teal accent) — `TopBorder` |
| Drawer top stripe | `--height-drawer-top-border` (~22px), `uic-drawer-top-border` / `DrawerTopBorder` |
| Drawer search | `--color-drawer-search` → `bg-drawer-search`, `--spacing-drawer-search-mt` (54px), `uic-drawer-search-input` |

## Phase gate

Phase 2 (Flask API) should only add data wiring — **not** new hardcoded colors or one-off spacing. New pages (state, bill) consume these tokens from day one.
