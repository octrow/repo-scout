"""`ui.table` + its own empty-state label, kept in sync by one call.

Both tlf's `/authors` and `/videos` pages build a `ui.table`, a matching
"nothing found" label, and a `_refresh()` that does the same three steps:
`table.rows = [...]`, `table.update()`, then toggle table/label visibility by
whether any rows matched. This is that plumbing, not the filtering logic
(which stays per-page — topic/status/text predicates are domain, not kit).

Wide tables fit the window instead of scrolling sideways (see DESIGN.md):
- `"sub": "<field>"` on a column puts a second, quieter line under the value,
  so related fields share one column (name + description);
- `"priority": 2 | 3` on a column hides it as the table gets narrower
  (CSS container query, `theme.TABLE_HIDE_P3_REM` / `TABLE_HIDE_P2_REM`); the
  row's detail view is where hidden fields stay reachable;
- `column_picker()` lets the user choose columns; a manual choice turns the
  width-based hiding off, and only then can the table scroll sideways, with the
  first column pinned.
"""

import json
from dataclasses import dataclass, field

from nicegui import ui

from . import layout
from .texts import tr

# Value + its `sub` field under it; a page's own `body-cell-<name>` slot still wins
SUB_SLOT = ('<q-td :props="props">{{ props.value }}'
            '<div v-if="props.col.sub" class="ic-cell-sub" :title="props.row[props.col.sub]">'
            '{{ props.row[props.col.sub] }}</div></q-td>')
PICKED_CLASS = "ic-table--picked"


def _decorate(columns: list[dict]) -> list[dict]:
    """Priority -> a class on th and td; the first column is the row's anchor, never hidden."""
    out = []
    for i, column in enumerate(columns):
        css = f"ic-p{column.get('priority', 1)}"
        extra = {"classes": f"{column.get('classes', '')} {css}".strip(),
                 "headerClasses": f"{column.get('headerClasses', '')} {css}".strip()}
        out.append({**column, **extra, **({"required": True} if i == 0 else {})})
    return out


@dataclass
class EmptyAwareTable:
    """A table + the label that replaces it when a filter matches nothing."""

    table: ui.table
    empty_label: ui.label
    hidden: set[str] | None = None  # None: columns follow the width; a set: the user's choice
    _picker: ui.column | None = field(default=None, repr=False)
    _storage_key: str = ""

    def set_rows(self, rows: list[dict]) -> None:
        """Push new rows and toggle table/empty-label visibility to match."""
        self.table.rows = rows
        self.table.update()
        has_rows = bool(rows)
        self.table.set_visibility(has_rows)
        self.empty_label.set_visibility(not has_rows)

    def set_columns(self, columns: list[dict]) -> None:
        """Replace the columns (e.g. drop one no row has a value for); keeps the user's choice."""
        self.table.columns = _decorate(columns)
        if any(c.get("sub") for c in columns) and "body-cell" not in self.table.slots:
            self.table.add_slot("body-cell", SUB_SLOT)
        self._apply()

    def _apply(self) -> None:
        names = [c["name"] for c in self.table.columns]
        self.table.props["visible-columns"] = [n for n in names if n not in (self.hidden or set())]
        if self.hidden is None:
            self.table.classes(remove=PICKED_CLASS)
        else:
            self.table.classes(add=PICKED_CLASS)
        self.table.update()
        if self._picker is not None:
            self._fill_picker()

    def column_picker(self, storage_key: str) -> ui.button:
        """A "Columns" button with a menu, at the caller's place (a filter bar).

        The choice lives in this browser's localStorage under `storage_key`.
        """
        with layout.button(tr("columns"), kind="quiet", size="row", icon="view_column") as button:
            with ui.menu(), ui.column().classes("ic-stack ic-menu-body") as self._picker:
                pass
        self._storage_key = storage_key
        self._fill_picker()

        async def _restore() -> None:
            try:
                saved = await ui.run_javascript(f"localStorage.getItem('{storage_key}')")
            except TimeoutError:
                return  # ponytail: a slow client keeps the width-based columns this visit
            try:
                hidden = json.loads(saved) if saved else None
            except ValueError:
                return
            if isinstance(hidden, list):
                self.hidden = {str(n) for n in hidden}
                self._apply()

        ui.context.client.on_connect(_restore)
        return button

    def _choose(self, hidden: set[str] | None) -> None:
        self.hidden = hidden
        key = self._storage_key
        ui.run_javascript(f"localStorage.removeItem('{key}')" if hidden is None
                          else f"localStorage.setItem('{key}', {json.dumps(json.dumps(sorted(hidden)))})")
        self._apply()

    def _fill_picker(self) -> None:
        assert self._picker is not None
        self._picker.clear()
        hidden = self.hidden or set()
        with self._picker:
            ui.checkbox(tr("fit_width"), value=self.hidden is None,
                        on_change=lambda e: self._choose(None if e.value else set()))
            ui.separator()
            for column in self.table.columns:
                if column.get("required"):
                    continue
                name = column["name"]
                ui.checkbox(column.get("label") or name, value=name not in hidden,
                            on_change=lambda e, n=name: self._choose(
                                (self.hidden or set()) - {n} if e.value else (self.hidden or set()) | {n}))


def empty_aware_table(
    columns: list[dict],
    *,
    row_key: str,
    pagination: dict | None = None,
    empty_text: str | None = None,
) -> EmptyAwareTable:
    """Build the table + label pair; call `.set_rows(...)` from your filter refresh."""
    table = ui.table(
        columns=_decorate(columns), rows=[], row_key=row_key, pagination=pagination or {},
    ).classes("w-full ic-table")
    # Quasar's own pagination texts follow only the language it started with
    table.props["rows-per-page-label"] = tr("rows_per_page")
    table.props[":pagination-label"] = f"(first, last, total) => `${{first}}-${{last}} {tr('of')} ${{total}}`"
    empty_label = ui.label(empty_text or tr("empty")).classes("t-status t-muted")  # with the kit theme: as layout.empty()
    empty_label.set_visibility(False)
    pair = EmptyAwareTable(table=table, empty_label=empty_label)
    pair.set_columns(columns)
    return pair
