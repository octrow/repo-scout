"""Colors + typography for every page. Call `apply_theme()` once, before ui.run().

One token dict per theme (light / dark): the CSS variables, the Quasar brand
colors and the contrast test (`tests/test_theme_layout.py`) all read it, so a
color is authored in exactly one place. Pages follow `ui.dark_mode`; add
`theme_toggle()` to a header to let the user pick system / light / dark.
"""

import re
from pathlib import Path

from nicegui import app, ui

from .texts import tr

# --- theme: colors + typography ---------------------------------------------
# One authored accent (deep teal-petrol, OKLCH 0.525 0.085 220) replaces the
# default framework blue. Warm = "внимание", red = "упало", green = "готово".
# Self-hosted Inter Variable (SIL OFL 1.1) + system mono stack, fully offline;
# degrades to a Cyrillic-safe system stack when the woff2 is absent.

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
FONT_FILE = FONT_DIR / "InterVariable.woff2"
THEME_STORAGE_KEY = "nicegui-kit-theme"  # localStorage: "light" / "dark"; absent = system

# Each token becomes `--ic-<name>`. Dark is the same accent re-authored for a
# dark canvas (lighter, so it still reads), not an inverted light theme.
TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "accent-100": "#DEF3FA", "accent-300": "#99CEDF", "accent-600": "#20758C",
        "accent-700": "#0A6175", "accent-800": "#004C5D",
        "canvas": "#F3F6F8", "surface": "#FFFFFF", "surface-sunken": "#EEF3F4",
        "border": "#D8DDDF", "border-strong": "#C6CED0",
        "text": "#262E31", "text-secondary": "#535D60", "text-muted": "#646E72",
        "run": "#845510", "ok": "#1C6E42", "err": "#A8372E", "idle": "#5B6569",
        "warn-bg": "#FEF5E8", "warn-border": "#D9B070", "warn-ink": "#684807",
        "fail-bg": "#FEF3F1", "fail-border": "#F8A59B", "fail-ink": "#6C1614",
        "fail-body": "#881A19",
        "on-fill": "#FFFFFF",  # text on a filled button / notification
    },
    "dark": {
        "accent-100": "#173F49", "accent-300": "#2F6B7A", "accent-600": "#5FB8CF",
        "accent-700": "#7CC8DC", "accent-800": "#A5DCEA",
        "canvas": "#13191B", "surface": "#1B2326", "surface-sunken": "#222B2E",
        "border": "#2E393D", "border-strong": "#3D4A4F",
        "text": "#E4EAEC", "text-secondary": "#AEB9BC", "text-muted": "#929DA1",
        "run": "#E0B062", "ok": "#6CC795", "err": "#F0877C", "idle": "#9DA8AC",
        "warn-bg": "#2D2414", "warn-border": "#6E5526", "warn-ink": "#EBC77F",
        "fail-bg": "#2E1A18", "fail-border": "#7A3A33", "fail-ink": "#F6B3AA",
        "fail-body": "#F0968B",
        "on-fill": "#13191B",
    },
}

# The only sizes on screen: spacing steps, control heights, content column.
# Helpers and CSS read these as `--ic-<name>`; pages never write px of their own.
SIZES = {"s1": 4, "s2": 8, "s3": 12, "s4": 16, "s6": 24, "s8": 32,
         "h-ctl": 40, "h-row": 28, "gutter": 24, "icon": 20}
# Touch screens get WCAG 2.2-comfortable targets (44 / 36) and a tighter gutter.
SIZES_COARSE = {"h-ctl": 44, "h-row": 36, "gutter": 16}
# Type scale (rem): 16px body floor, ~1.125-1.25 steps; roles in the CSS use only these.
TYPE_SCALE = {"fs-xs": 0.8125, "fs-sm": 0.875, "fs-ui": 0.9375, "fs-base": 1,
              "fs-md": 1.125, "fs-lg": 1.375, "fs-xl": 1.75}
# Motion: short, ease-out, never blocking; prefers-reduced-motion turns it off.
MOTION = {"dur-fast": "120ms", "dur-base": "200ms", "dur-slow": "320ms",
          "ease-out": "cubic-bezier(0.16, 1, 0.3, 1)",
          "ease-in-out": "cubic-bezier(0.65, 0, 0.35, 1)"}
# Weights, leading and tracking: every text role is a combination of these.
WEIGHTS = {"fw-regular": 400, "fw-medium": 500, "fw-semibold": 600, "fw-bold": 650}
LEADING = {"lh-tight": 1.2, "lh-snug": 1.35, "lh-dense": 1.45, "lh-base": 1.5, "lh-read": 1.65}
TRACKING = {"ls-tight": "-0.02em", "ls-snug": "-0.01em", "ls-wide": "0.01em", "ls-caps": "0.04em"}
# Corners (px) and elevation: hairline borders do the work, shadows only lift overlays.
RADII = {"r-sm": 4, "r-md": 6, "r-lg": 8, "r-pill": 999}
SHADOWS = {"shadow-menu": "0 6px 20px rgb(0 0 0 / 0.10)", "shadow-dialog": "0 12px 40px rgb(0 0 0 / 0.18)"}
# Content measures: reading width, smallest dialog / select / grid column.
MEASURES = {"measure": "68ch", "dialog-min": "20rem", "select-min": "10rem", "col-min": "18rem",
            "cell-max": "28rem",
            "cell-share": "30cqi"}  # a text cell takes at most this share of its table
GRID_COLUMNS = 12
GRID_COLLAPSE_PX = 700  # narrower: every grid becomes one column
# Table width (rem) below which priority-3, then priority-2 columns hide (table.py)
TABLE_HIDE_P3_REM = 80
TABLE_HIDE_P2_REM = 56

# (text, background) pairs that must read at 4.5:1 (WCAG AA) in both themes.
_INKS = ("text", "text-secondary", "text-muted", "accent-600", "accent-700",
         "run", "ok", "err", "idle")
TEXT_PAIRS = [(fg, bg) for fg in _INKS for bg in ("canvas", "surface", "surface-sunken")] + [
    ("warn-ink", "warn-bg"), ("fail-ink", "fail-bg"), ("fail-body", "fail-bg"),
    ("text", "accent-100"), ("accent-800", "accent-100"),
] + [("on-fill", bg) for bg in ("accent-600", "err", "ok", "run", "text-secondary")]

# Quasar brand colors point at the tokens, so `color=primary` follows the theme.
_COLORS = dict(
    primary="var(--ic-accent-600)",
    secondary="var(--ic-text-secondary)",
    accent="var(--ic-accent-700)",
    positive="var(--ic-ok)",
    negative="var(--ic-err)",
    warning="var(--ic-run)",
    info="var(--ic-accent-600)",  # info == accent, not cyan (Quasar default fails AA)
    dark="var(--ic-surface)",
    dark_page="var(--ic-canvas)",
)

# header button cycles these: mode -> (icon, tooltip)
THEME_MODES = {"system": ("brightness_auto", "theme_system"),
               "light": ("light_mode", "theme_light"),
               "dark": ("dark_mode", "theme_dark")}  # text: a `texts` key


def luminance(hex_color: str) -> float:
    """WCAG relative luminance of #RRGGBB."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two #RRGGBB colors (1..21)."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _vars(theme: str) -> str:
    return " ".join(f"--ic-{k}: {v};" for k, v in TOKENS[theme].items())


def _token_css() -> str:
    sizes = " ".join(f"--ic-{k}: {v}px;" for k, v in SIZES.items())
    coarse = " ".join(f"--ic-{k}: {v}px;" for k, v in SIZES_COARSE.items())
    scale = " ".join(f"--ic-{k}: {v}rem;" for k, v in TYPE_SCALE.items())
    motion = " ".join(f"--ic-{k}: {v};" for k, v in {**MOTION, **WEIGHTS, **LEADING, **TRACKING,
                                                      **SHADOWS, **MEASURES}.items())
    radii = " ".join(f"--ic-{k}: {v}px;" for k, v in RADII.items())
    spans = "\n".join(f".ic-grid-12 > .ic-span-{n} {{ grid-column: span {n}; }}"
                      for n in range(1, GRID_COLUMNS + 1))
    return (f":root {{ {_vars('light')} {sizes} {scale} {motion} {radii} color-scheme: light; }}\n"
            f"body.body--dark {{ {_vars('dark')} color-scheme: dark; }}\n"
            f"@media (pointer: coarse) {{ :root {{ {coarse} }} }}\n"
            f".nicegui-column.ic-grid-12, .nicegui-column.ic-grid {{ display: grid; width: 100%;"
            f" gap: var(--ic-gutter); align-items: stretch; }}\n"
            f".nicegui-column.ic-grid-12 {{ grid-template-columns: repeat({GRID_COLUMNS}, minmax(0, 1fr)); }}\n"
            f".nicegui-column.ic-grid {{ grid-template-columns:"
            f" repeat(auto-fill, minmax(min(var(--ic-col-min), 100%), 1fr)); }}\n"
            f"{spans}\n"
            f"@media (max-width: {GRID_COLLAPSE_PX - 1}px) {{ .ic-grid-12 > [class*='ic-span-']"
            f" {{ grid-column: 1 / -1; }} }}\n"
            f"@container ic-table (max-width: {TABLE_HIDE_P3_REM}rem) {{"
            f" .ic-table:not(.ic-table--picked) .ic-p3 {{ display: none; }} }}\n"
            f"@container ic-table (max-width: {TABLE_HIDE_P2_REM}rem) {{"
            f" .ic-table:not(.ic-table--picked) :is(.ic-p2, .ic-p3) {{ display: none; }} }}\n")


_FONT_FACE_CSS = """
@font-face {
  font-family: "InterVariable";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: local("InterVariable"), local("Inter var"),
       url("/fonts/InterVariable.woff2") format("woff2");
}
"""

# Class prefix is `ic-` (incident_collect, the source this kit was extracted
# from) - kept as-is on purpose: renaming would be pure diff noise with zero
# behavior change. See README for the full class list.
# Gaps live here, on classes, never as Tailwind gap-* (NiceGUI #2171).
_THEME_CSS = """
:root {
  --ic-sans: "InterVariable", "Inter", -apple-system, BlinkMacSystemFont,
             "Segoe UI Variable Text", "Segoe UI", Roboto, "Noto Sans",
             "Liberation Sans", "DejaVu Sans", Arial, sans-serif;
  --ic-mono: ui-monospace, "SF Mono", "Cascadia Mono", "Segoe UI Mono",
             "JetBrains Mono", Consolas, "DejaVu Sans Mono", "Liberation Mono",
             "Noto Sans Mono", "Courier New", monospace;
}

/* --- base: 16px floor, beats Quasar's body 14px --------------------------- */
html { font-size: 100%; scrollbar-gutter: stable; }
body, body.body--dark {
  font-family: var(--ic-sans);
  font-size: var(--ic-fs-base);
  line-height: var(--ic-lh-base);
  font-optical-sizing: auto;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}
body, body.body--dark, .q-page, .nicegui-content { background: var(--ic-canvas); color: var(--ic-text); }

.q-field, .q-field__native, .q-field__input, .q-field__label,
.q-field__prefix, .q-field__suffix, .q-item__label, .q-btn, .q-tooltip,
.q-notification, .q-radio__label, .q-checkbox__label, .q-menu, .q-dialog {
  font-family: inherit;
}
.q-field, .q-field__native, .q-field__input, .q-field__label,
.q-radio__label, .q-checkbox__label {
  font-size: var(--ic-fs-base);
  line-height: var(--ic-lh-base);
}
.q-field__bottom { font-size: var(--ic-fs-xs); color: var(--ic-text-muted); }
.q-btn, .q-btn__content, .q-tab, .q-tab__label, .q-chip, .q-toggle {
  text-transform: none;   /* Quasar shouts by default; Russian labels suffer */
}
.q-btn, .q-btn__content {
  font-size: var(--ic-fs-ui);
  font-weight: var(--ic-fw-semibold);
  letter-spacing: var(--ic-ls-wide);
}
.q-btn .q-icon { font-size: var(--ic-icon); }
.q-btn.ic-btn-ctl { min-height: var(--ic-h-ctl); padding: 0 var(--ic-s4); }
.q-btn.ic-btn-row { min-height: var(--ic-h-row); padding: 0 var(--ic-s3); }
.q-btn.ic-btn-row.q-btn--flat { padding: 0 var(--ic-s2); }
.q-btn--round.ic-btn-ctl { width: var(--ic-h-ctl); padding: 0; }
/* Filled controls: their ink comes from the token, not Quasar's fixed white,
   so a filled button still reads on the lighter dark-theme accent. Set on the
   children: Quasar's `.text-white` is a layered !important we can't outrank. */
.text-white:is(.bg-primary, .bg-secondary, .bg-accent, .bg-positive,
               .bg-negative, .bg-warning, .bg-info) > * { color: var(--ic-on-fill); }

/* --- surfaces: flat, a border instead of a shadow, same in both themes ---- */
.q-card, .q-menu, .q-header, .q-drawer, .q-footer, .q-dialog .q-card,
.q-expansion-item, .q-table__card, .q-list {
  background: var(--ic-surface); color: var(--ic-text);
}
.q-card { border: 1px solid var(--ic-border); border-radius: var(--ic-r-lg); box-shadow: none; }
.q-menu { border: 1px solid var(--ic-border); box-shadow: var(--ic-shadow-menu); }
.q-dialog .q-card { box-shadow: var(--ic-shadow-dialog); }
.q-header { border-bottom: 1px solid var(--ic-border); box-shadow: none; }
.q-drawer { border-right: 1px solid var(--ic-border); }
.q-footer { border-top: 1px solid var(--ic-border); box-shadow: none; }
.q-separator { background: var(--ic-border); }
.q-tooltip {
  background: var(--ic-text); color: var(--ic-canvas);
  font-size: var(--ic-fs-xs); padding: var(--ic-s1) var(--ic-s2); border-radius: var(--ic-r-sm);
}
body.body--dark .q-field__native, body.body--dark .q-field__label,
body.body--dark .q-field__control, body.body--dark .q-item,
body.body--dark .q-table { color: var(--ic-text); }
.q-field--outlined .q-field__control:before { border-color: var(--ic-border-strong); }
.q-field--outlined:hover .q-field__control:before { border-color: var(--ic-text-muted); }

/* --- tables: quiet header, aligned numbers ---------------------------------*/
.q-table__card { box-shadow: none; }
.q-table__container { background: transparent; }
.q-table th {
  font-size: var(--ic-fs-xs); font-weight: var(--ic-fw-semibold); color: var(--ic-text-secondary);
  letter-spacing: var(--ic-ls-wide);
}
.q-table td, .q-table th, .q-table__bottom { border-color: var(--ic-border); }
.q-table tbody td { font-size: var(--ic-fs-ui); font-variant-numeric: tabular-nums; }
.q-table tbody tr:hover td { background: var(--ic-surface-sunken); }
.q-table--no-wrap td { white-space: normal; }
/* wide tables fit the window (table.py): the table is the size container its
   priority columns hide in; a second line under a value; the first column stays
   pinned when a manual column choice makes the table scroll sideways */
.q-table__container.ic-table { container: ic-table / inline-size; }
.ic-cell-sub { max-width: min(var(--ic-cell-max), var(--ic-cell-share)); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; font-size: var(--ic-fs-sm); color: var(--ic-text-secondary); }
.ic-table .q-table tr > :first-child { position: sticky; left: 0; z-index: 1;
  background: var(--ic-surface); border-right: 1px solid var(--ic-border); }
.ic-table .q-table tbody tr:hover > td:first-child { background: var(--ic-surface-sunken); }
.ic-menu-body { padding: var(--ic-s2) var(--ic-s3); }

/* --- links, focus, selection, scrollbars -----------------------------------*/
a, a:visited { color: var(--ic-accent-700); text-decoration-color: var(--ic-accent-300);
               text-underline-offset: 0.18em; }
a:hover { color: var(--ic-accent-800); text-decoration-color: currentColor; }
:focus-visible {
  outline: 2px solid var(--ic-accent-600);
  outline-offset: 2px;
  border-radius: var(--ic-r-sm);
}
.q-field--focused .q-field__control:after { border-color: var(--ic-accent-600); }
::selection { background: var(--ic-accent-100); color: var(--ic-text); }
* { scrollbar-width: thin; scrollbar-color: var(--ic-border-strong) transparent; }
input, textarea { caret-color: var(--ic-accent-600); }

/* --- layout: the page column, cards, rows; gaps from the spacing scale -----*/
.nicegui-column.ic-page {
  width: 100%; margin-inline: auto; align-items: stretch;
  gap: var(--ic-s6); padding: var(--ic-s6) var(--ic-s6) var(--ic-s8);
}
.q-dialog .q-card.ic-card { width: auto; min-width: min(var(--ic-dialog-min), 100%); }
.q-card.ic-card { width: 100%; align-items: stretch; gap: var(--ic-s4); padding: var(--ic-s4); }
/* a lone card in a grid cell takes the row's height: side-by-side cards end level */
:is(.ic-grid-12, .ic-grid) > .nicegui-column > .q-card.ic-card:only-child { flex: 1 1 auto; }
.q-card.ic-card--recessive { background: var(--ic-surface-sunken); border-color: transparent; }
.nicegui-column.ic-stack { width: 100%; align-items: stretch; gap: var(--ic-s2); }
.nicegui-row.ic-actions { width: 100%; justify-content: flex-end; align-items: center; gap: var(--ic-s2); }
.nicegui-row.ic-actions.ic-actions--start { justify-content: flex-start; }
.nicegui-row.ic-state { align-items: center; flex-wrap: nowrap; gap: var(--ic-s3); padding: var(--ic-s2) 0; }
.ic-state > div { min-width: 0; }   /* the words wrap; icon and button stay put */
.ic-state > .q-icon, .ic-state > .q-btn, .ic-state > .q-spinner { flex: none; }
.nicegui-row.ic-split { width: 100%; align-items: center; justify-content: space-between;
                        gap: var(--ic-s4); }
@media (max-width: 599px) {
  .nicegui-column.ic-page { padding: var(--ic-s4) var(--ic-s4) var(--ic-s6); gap: var(--ic-s4); }
}

/* --- role ramp ------------------------------------------------------------ */
h1, .t-title-page {
  font-family: var(--ic-sans);
  font-size: var(--ic-fs-xl);
  line-height: var(--ic-lh-tight);
  font-weight: var(--ic-fw-bold);
  letter-spacing: var(--ic-ls-tight);
  margin: 0;
  text-wrap: balance;
}
h2, .t-title-section {
  font-family: var(--ic-sans);
  font-size: var(--ic-fs-md);
  line-height: var(--ic-lh-snug);
  font-weight: var(--ic-fw-semibold);
  letter-spacing: var(--ic-ls-snug);
  margin: 0;
  text-wrap: balance;
}
/* h3 only via the class: a bare h3 in markdown keeps reading as a heading */
.t-title-group {
  font-family: var(--ic-sans);
  font-size: var(--ic-fs-xs);
  line-height: var(--ic-lh-dense);
  font-weight: var(--ic-fw-semibold);
  letter-spacing: var(--ic-ls-caps);
  text-transform: uppercase;
  color: var(--ic-text-secondary);
  margin: 0;
}
.t-status {
  font-size: var(--ic-fs-base);
  line-height: var(--ic-lh-dense);
  font-weight: var(--ic-fw-semibold);
  letter-spacing: normal;
  font-variant-numeric: tabular-nums;
}
.t-meta {
  font-size: var(--ic-fs-sm);
  line-height: var(--ic-lh-dense);
  font-weight: var(--ic-fw-medium);
  letter-spacing: normal;
  color: var(--ic-text-secondary);
  font-variant-numeric: tabular-nums;
}
.t-muted { color: var(--ic-text-muted); }
.t-mono {
  font-family: var(--ic-mono);
  font-size: var(--ic-fs-sm);
  line-height: var(--ic-lh-base);
  font-variant-ligatures: none;
  font-feature-settings: "zero" 1;
  overflow-wrap: anywhere;
}
.t-brand { font-weight: var(--ic-fw-bold); letter-spacing: var(--ic-ls-snug); white-space: nowrap; }
/* header navigation: the current page is ink + an underline, not colour alone */
a.ic-nav-link, a.ic-nav-link:visited { white-space: nowrap;
  color: var(--ic-text-secondary); text-decoration: none; font-weight: var(--ic-fw-semibold);
  padding: var(--ic-s2) var(--ic-s1); border-bottom: 2px solid transparent;
}
a.ic-nav-link:hover { color: var(--ic-text); }
a.ic-nav-link.ic-nav-link--here { color: var(--ic-text); border-bottom-color: var(--ic-accent-600); }

/* --- status line states ----------------------------------------------------*/
.ic-status--running { color: var(--ic-run); }
.ic-status--ok      { color: var(--ic-ok); }
.ic-status--cancel  { color: var(--ic-idle); }
.ic-status--error   { color: var(--ic-err); }
.ic-status--idle    { color: var(--ic-idle); font-weight: var(--ic-fw-regular); }

/* --- status badge: the status ink on a 10% tint of itself (pairs with ic-status--*) */
.ic-badge {
  display: inline-flex; align-items: center; flex: none;
  padding: 0 var(--ic-s2); border-radius: var(--ic-r-pill); white-space: nowrap;
  font-size: var(--ic-fs-sm); line-height: var(--ic-lh-base); font-weight: var(--ic-fw-semibold); font-variant-numeric: tabular-nums;
  background: color-mix(in srgb, currentColor 10%, transparent);
}

/* --- chips -------------------------------------------------------------*/
.ic-chip {
  display: inline-flex; align-items: center;
  padding: 1px var(--ic-s2); border-radius: var(--ic-r-pill);
  font-size: var(--ic-fs-xs); line-height: var(--ic-lh-dense); font-weight: var(--ic-fw-semibold);
  letter-spacing: var(--ic-ls-wide); white-space: nowrap;
  border: 1px solid transparent;
}
.ic-chip--neutral { background: var(--ic-surface-sunken); border-color: var(--ic-border-strong); color: var(--ic-text-secondary); }
.ic-count {
  display: inline-block; min-width: 1.5em; padding: 0 var(--ic-s2);
  border-radius: var(--ic-r-pill); text-align: center;
  background: var(--ic-accent-100); color: var(--ic-text);
  font-size: var(--ic-fs-xs); font-weight: var(--ic-fw-semibold); font-variant-numeric: tabular-nums;
}

/* --- warning banner, failure card, reassurance -----------------------------*/
.ic-banner {
  background: var(--ic-warn-bg);
  color: var(--ic-warn-ink);
  border: 1px solid var(--ic-warn-border);
  border-radius: var(--ic-r-sm);
}
.q-card.ic-failure { background: var(--ic-fail-bg); border: 1px solid var(--ic-fail-border); }
.ic-failure-title { color: var(--ic-fail-ink); font-weight: var(--ic-fw-semibold); }
.ic-failure-body  { color: var(--ic-fail-body); }
.ic-reassure { color: var(--ic-text-muted); font-size: var(--ic-fs-xs); font-weight: var(--ic-fw-regular); }

/* --- diagnostics: ok is quiet, not-ok warns (never blocks) -----------------*/
.ic-diag-ok   { color: var(--ic-text-muted); }
.ic-diag-warn { color: var(--ic-warn-ink); font-weight: var(--ic-fw-medium); }

/* --- run list: one bordered row per run ------------------------------------*/
.q-expansion-item.ic-run { border: 1px solid var(--ic-border); border-radius: var(--ic-r-lg); overflow: hidden; }
/* One inset only: the panel's left edge = the run title's (q-item's 16px); NiceGUI's
   own content padding would add a second one. */
.q-expansion-item.ic-run .q-expansion-item__content { padding: 0; }
.ic-run .nicegui-expansion-content { padding: 0 var(--ic-s4) var(--ic-s3); }
.nicegui-row.ic-run-head { flex: 1; min-width: 0; align-items: center; flex-wrap: nowrap;
                           gap: var(--ic-s3); padding-right: var(--ic-s2); }
.ic-run-title { flex: 1 1 auto; min-width: 0; font-weight: var(--ic-fw-semibold); overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap; }
/* inside a run the log is a flat sunken panel: no second frame in the frame.
   Fixed height: ui.log is a QScrollArea (absolute content), it can't size to its lines. */
.ic-run-time { flex: none; min-width: 3.5em; text-align: right; }
.nicegui-column.ic-log-panel { gap: 0; border-radius: var(--ic-r-md); overflow: hidden;
                               background: var(--ic-surface-sunken); }
.nicegui-row.ic-log-head { padding: var(--ic-s1) var(--ic-s2) var(--ic-s1) var(--ic-s3);
                           border-bottom: 1px solid var(--ic-border); flex-wrap: nowrap; }
.nicegui-row.ic-log-head > .ic-actions { width: auto; flex: none; }
.ic-log-caption { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.ic-run .nicegui-log { border: none; outline: none; border-radius: 0; background: transparent;
  height: calc(var(--ic-log-lines, 3) * var(--ic-fs-xs) * var(--ic-lh-dense) + 2 * var(--ic-s2)); }
/* lines start on the caption's edge; 8px top + bottom = the 1rem in the height above */
.ic-run .nicegui-log .q-scrollarea__content { padding: var(--ic-s2) var(--ic-s3); }

/* --- log + CLI command (density surfaces) ----------------------------------*/
.nicegui-log .q-scrollarea__content, .t-log {
  font-family: var(--ic-mono);
  font-size: var(--ic-fs-xs);
  line-height: var(--ic-lh-dense);
  font-variant-ligatures: none;
}
.t-log { white-space: pre-wrap; overflow-wrap: anywhere; }
.nicegui-log {
  background: var(--ic-surface-sunken); border: 1px solid var(--ic-border);
  border-radius: var(--ic-r-md); color: var(--ic-text);
}
.t-command code, .t-command pre {
  font-family: var(--ic-mono);
  font-size: var(--ic-fs-xs);
  line-height: var(--ic-lh-base);
  font-variant-ligatures: none;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* --- markdown bundles: read surface ----------------------------------------*/
.md-body { font-size: var(--ic-fs-base); line-height: var(--ic-lh-read); overflow-wrap: anywhere; }
.md-body > p, .md-body > ul, .md-body > ol, .md-body > blockquote,
.md-body > h1, .md-body > h2, .md-body > h3,
.md-body > h4, .md-body > h5, .md-body > h6 {
  max-width: var(--ic-measure);
}
.md-body h1 { font-size: var(--ic-fs-md); line-height: var(--ic-lh-snug);  font-weight: var(--ic-fw-bold); letter-spacing: var(--ic-ls-snug);  margin: var(--ic-s8) 0 var(--ic-s2); }
.md-body h2 { font-size: var(--ic-fs-base); line-height: var(--ic-lh-snug); font-weight: var(--ic-fw-semibold); letter-spacing: var(--ic-ls-snug); margin: var(--ic-s6) 0 var(--ic-s2); }
.md-body h3 { font-size: var(--ic-fs-base);      line-height: var(--ic-lh-dense);  font-weight: var(--ic-fw-bold); margin: var(--ic-s6) 0 var(--ic-s1); }
.md-body h4, .md-body h5, .md-body h6 { font-size: var(--ic-fs-base); line-height: var(--ic-lh-dense); font-weight: var(--ic-fw-semibold); margin: var(--ic-s4) 0 var(--ic-s1); }
.md-body > :first-child { margin-top: 0; }
.md-body p  { margin: var(--ic-s3) 0; }
/* GitHub READMEs float logos with <img align>: keep images in the flow and inside the column */
.md-body > .nicegui-markdown { width: 100%; min-width: 0; }  /* else a wide image sizes the flex item, and 100% is moot */
.md-body img { max-width: 100%; height: auto; float: none; vertical-align: middle; }
.md-body li { margin: var(--ic-s1) 0; }
.md-body blockquote {
  margin: var(--ic-s3) 0; padding: 0 var(--ic-s4);
  border-left: 1px solid var(--ic-border-strong); color: var(--ic-text-secondary);
}
.md-body table {
  display: block;
  width: max-content;
  max-width: 100%;
  overflow-x: auto;
  font-size: var(--ic-fs-sm);
  line-height: var(--ic-lh-dense);
  font-variant-numeric: tabular-nums;
}
.md-body th { font-weight: var(--ic-fw-semibold); text-align: left; white-space: nowrap; }
.md-body th, .md-body td { overflow-wrap: normal; border-color: var(--ic-border); }   /* scroll, don't shred uuids */
.md-body code {
  font-family: var(--ic-mono);
  font-size: 0.875em;
  font-variant-ligatures: none;
  background: var(--ic-surface-sunken);
  padding: 0.08em 0.3em;
  border-radius: var(--ic-r-sm);
}
.md-body pre, .md-body .codehilite {
  max-width: 100%; overflow-x: auto;
  background: var(--ic-surface-sunken); border-radius: var(--ic-r-md); padding: var(--ic-s3) var(--ic-s4);
}
.md-body pre code { background: none; padding: 0; font-size: var(--ic-fs-xs); line-height: var(--ic-lh-base); }

/* --- filter bar: one control height across toggle, select and search --------*/
.nicegui-row.ic-filters { width: 100%; align-items: center; flex-wrap: wrap; gap: var(--ic-s2) var(--ic-s3); }
.ic-filters .q-field--dense .q-field__control,
.ic-filters .q-btn-toggle,
.ic-filters .q-btn-toggle .q-btn { min-height: var(--ic-h-ctl); }
/* Selected segment reads as a fill, not as a colour change alone. */
.ic-filters .q-btn-toggle {
  border: 1px solid var(--ic-border-strong);
  border-radius: var(--ic-r-sm);
}
.ic-filters .q-select { min-width: var(--ic-select-min); }
/* Toggle selection (toggle-color=ic-sel, set in apply_theme): a tonal fill plus
   weight, so it never competes with the screen's one primary button. */
.bg-ic-sel { background: var(--ic-accent-100); }
.text-ic-sel-ink { color: var(--ic-accent-800); font-weight: var(--ic-fw-semibold); }
.q-btn-group { box-shadow: none; }

/* Stacked filters must not be three different widths. */
@media (max-width: 699px) {
  .ic-filters > * { width: 100%; }
  .ic-filters .q-btn-toggle .q-btn { flex: 1; }
}

/* --- motion: state changes ease out, presses answer at once -----------------*/
.q-btn, .q-field__control, .q-field__control:before, .q-field__control:after, a,
.q-item, .q-tab, .q-table tbody td, .q-expansion-item__container > .q-item {
  transition: background-color var(--ic-dur-fast) var(--ic-ease-out),
              color var(--ic-dur-fast) var(--ic-ease-out),
              border-color var(--ic-dur-fast) var(--ic-ease-out),
              box-shadow var(--ic-dur-fast) var(--ic-ease-out),
              transform var(--ic-dur-fast) var(--ic-ease-out);
}
.q-btn:not(.disabled):active { transform: translateY(1px); }
.q-expansion-item__toggle-icon { transition: transform var(--ic-dur-base) var(--ic-ease-out); }
.ic-appear { animation: ic-appear var(--ic-dur-base) var(--ic-ease-out) both; }
@keyframes ic-appear { from { opacity: 0; transform: translateY(4px); } }

/* --- fields: label above-the-fold, hint below, error replaces hint ----------*/
.q-field--error .q-field__bottom, .q-field--error .q-field__messages { color: var(--ic-err); }
.q-field--error .q-field__control:after { border-color: var(--ic-err); }
.ic-required .q-field__label::after { content: " *"; color: var(--ic-err); }
.q-field__native::placeholder { color: var(--ic-text-muted); opacity: 1; }
.q-field--outlined .q-field__control { border-radius: var(--ic-r-md); }

/* --- accessibility helpers ---------------------------------------------------*/
.ic-sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
:target { scroll-margin-top: calc(var(--ic-s8) * 2); }

/* segmented toggles never push the page sideways on a phone */
.q-btn-toggle { max-width: 100%; }
@media (max-width: 599px) {
  .q-btn-toggle .q-btn { flex: 1 1 auto; padding: 0 var(--ic-s2); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
"""


def css() -> str:
    """The whole kit stylesheet (tokens for both themes + rules), without the font face."""
    return _token_css() + _THEME_CSS


# A declaration that bypasses the tokens: a literal weight / leading / tracking / radius /
# shadow / font size, a rem or px gap (1px and 2px hairlines are fine), or a literal color.
# em stays allowed: it is relative to the text it sits in, not a new size.
_RAW_VALUE = re.compile(
    r"(?:font-weight|line-height|letter-spacing|border-radius|box-shadow)\s*:\s*(?!0\s*[;}])-?\.?\d[^;}]*"
    r"|font-size\s*:\s*[\d.]+(?:rem|px)"
    r"|(?:margin|padding|gap)[\w-]*\s*:[^;}]*?(?<![\w.-])(?:[3-9]|\d{2,}|\d*\.\d+)px[^;}]*"
    r"|(?:margin|padding|gap)[\w-]*\s*:[^;}]*?[\d.]+rem[^;}]*"
    r"|#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(")


def raw_values(css_text: str) -> list[str]:
    """Declarations in `css_text` that write a value instead of a `--ic-*` token.

    Apps run their own page CSS through it in a test, so every window shares one
    type, spacing, radius and color system: `assert theme.raw_values(MY_CSS) == []`.
    """
    return [m.group(0).strip() for m in _RAW_VALUE.finditer(css_text)]


def apply_theme() -> None:
    """Install colors + type on every page, in <head> (no flash of unstyled text).

    Call this explicitly, once, before `ui.run()` - not at import time: the
    caller decides when (and whether) to theme its app.
    """
    app.colors(**_COLORS)
    ui.toggle.default_props("toggle-color=ic-sel toggle-text-color=ic-sel-ink")
    style = css()
    if FONT_FILE.is_file():
        app.add_static_files("/fonts", str(FONT_DIR))
        style = _FONT_FACE_CSS + style
    ui.add_head_html(f"<style>{style}</style>", shared=True)


def theme_toggle() -> ui.button:
    """Round header button: system -> light -> dark -> system.

    The choice lives in this browser's localStorage (no storage_secret needed)
    and is restored on every page load. Call once per page, inside the header.
    """
    dark = ui.dark_mode(None)
    state = {"mode": "system", "restored": False}
    # color=None: header ink, not the accent - the toggle is never the page's main action
    button = ui.button(icon=THEME_MODES["system"][0], color=None).props("flat round").classes("ic-btn-ctl")
    with button:
        tooltip = ui.tooltip(tr(THEME_MODES["system"][1]))
    button.props(f'aria-label="{tr(THEME_MODES["system"][1])}"')

    def _show(mode: str) -> None:
        state["mode"] = mode
        dark.set_value({"light": False, "dark": True}.get(mode))
        icon, key = THEME_MODES[mode]
        words = tr(key)
        button.props(f'icon={icon} aria-label="{words}"')
        tooltip.set_text(words)

    def _next() -> None:
        modes = list(THEME_MODES)
        mode = modes[(modes.index(state["mode"]) + 1) % len(modes)]
        _show(mode)
        key = THEME_STORAGE_KEY
        ui.run_javascript(f"localStorage.removeItem('{key}')" if mode == "system"
                          else f"localStorage.setItem('{key}', '{mode}')")

    async def _restore() -> None:
        # ponytail: restored after the handshake, so a non-system choice flashes the
        # system theme on load; a pre-paint <head> script if that ever bothers
        if state["restored"]:  # on_connect fires again on every reconnect
            return
        state["restored"] = True
        try:
            saved = await ui.run_javascript(f"localStorage.getItem('{THEME_STORAGE_KEY}')")
        except TimeoutError:
            return  # ponytail: slow client keeps the system theme for this visit
        if saved in THEME_MODES:
            _show(saved)

    button.on_click(_next)
    ui.context.client.on_connect(_restore)
    return button
