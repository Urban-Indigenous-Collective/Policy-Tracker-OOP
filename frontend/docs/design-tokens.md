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
| `--width-state-drawer` | 523px (`w-state-drawer max-w-[100vw]`) |
| `--spacing-drawer-x` | 63px horizontal inset |
| Typography | `uic-drawer-state-title` (34px / bold mono), `uic-drawer-policies-count`, `uic-drawer-bill-id`, `uic-drawer-bill-session` (14px, 0.1em tracking) above the description, `uic-drawer-bill-body-regular` (16px / 28px leading) |
| Bill row | grid 158px + 40px gap + title col; row width `--width-drawer-content` (397px) |
| Chrome | `/ui/dismiss.svg`; status pill `--width/height-drawer-status-pill`; FILTER pill 95×23 with 14px inset, centered label + `--tracking-drawer-filter` end-padding; filter menu stays inside the content gutters |
| Site top bar | `--height-top-border` (3px teal accent) — `TopBorder` |
| Drawer top stripe | `--height-drawer-top-border` (~22px), `uic-drawer-top-border` / `DrawerTopBorder` |
| Drawer search | `--color-drawer-search` → `bg-drawer-search`, `--spacing-drawer-search-mt` (54px), `uic-drawer-search-input` |

## Policy list (Figma MacBook Pro 14" - 35)

| Token | Value |
|--------|--------|
| `--spacing-policy-list-top` | 56px below nav band |
| FILTER pill | Same as drawer: `--tracking-drawer-filter` (0.41em), `uic-drawer-filter-pill-label` on inner span |
| `--height-policy-list-toolbar-row` | 38px filter/search control row (`202:6591`) |
| `--spacing-policy-list-toolbar-to-content` | 48px below toolbar row before first state title (`202:6522`: filter row y=200 → title y=248) |
| `--max-width-policy-list` | 1260px content column (394 + 317 + 549) |
| `--spacing-policy-list-col-gap` | 317px between state title block and bill rows |
| `--spacing-policy-list-section-gap` | 199px below each state block (last bill or view-more → next title; Figma `202:6522`) |
| `--spacing-policy-list-section` | deprecated alias of `--spacing-policy-list-section-gap` |
| `--spacing-policy-list-header-to-rows` | 44px below stats before bill list (mobile stack) |
| `--spacing-policy-list-expand-mt` / `-label-gap` | View-more label and chevron spacing (`expand-mt` 97px / 6.0625rem above centered expand row) |
| `--tracking-policy-list-expand` | 7.38px — `uic-policy-list-expand-label` (Figma `202:6586`; centered on full section via `lg:col-span-2`) |
| Bill rows | Full width of the right grid column (~549px at 1260px content); id/pill column reuses drawer tokens (`--width-drawer-bill-col-id`, `--spacing-drawer-bill-col-gap`); title uses remaining `1fr` — not capped at `--width-drawer-content` |

## Bill detail (Figma `161:4181`, MacBook Pro 14" - 20)

| Token / class | Value |
|--------|--------|
| Panel frame | `--width-bill-panel` (1004px on the 1512 frame). At large breakpoints it fills from the left edge to the state drawer and slides with the drawer motion. Dismiss offset is `--spacing-bill-panel-pt`. |
| Content column | `--max-width-bill-panel` (893px) with `--spacing-bill-inset` (111px) left and `--spacing-bill-dismiss-end` (57px) right |
| Bill number | `uic-bill-number` — Roboto Mono SemiBold 55px, 30% tracking, accent |
| Title | `uic-bill-title` — Montserrat Medium 18 / 31, max 408px |
| Pills | `uic-bill-pill` — 25px outline, 13px semibold, 30px radius, 14px gap. Status uses `StatusBadge` + `text-status-*`. Qualitative pills use accent and the stored answer. |
| Summary / Pros / Cons | `uic-bill-detail-grid` — shared two-column grid (`uic-bill-summary-label` + `uic-bill-summary-body`); 110px column gap; body max 473px |
| Metadata rows | Same grid with `uic-bill-detail-grid--meta`; `uic-bill-meta-label` / `uic-bill-meta-body` (18 / 31) |
| Search | `--size-bill-search` (18px) accent icon linking to the official overview |

## Phase gate

Phase 2 (Flask API) should only add data wiring — **not** new hardcoded colors or one-off spacing. New pages (state, bill) consume these tokens from day one.
