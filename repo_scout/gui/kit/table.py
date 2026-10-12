"""`ui.table` + its own empty-state label, kept in sync by one call.

Both tlf's `/authors` and `/videos` pages build a `ui.table`, a matching
"nothing found" label, and a `_refresh()` that does the same three steps:
`table.rows = [...]`, `table.update()`, then toggle table/label visibility by
whether any rows matched. This is that plumbing, not the filtering logic
(which stays per-page — topic/status/text predicates are domain, not kit).
"""

from dataclasses import dataclass

from nicegui import ui

DEFAULT_EMPTY_TEXT = "nothing found."


@dataclass
class EmptyAwareTable:
    """A table + the label that replaces it when a filter matches nothing."""

    table: ui.table
    empty_label: ui.label

    def set_rows(self, rows: list[dict]) -> None:
        """Push new rows and toggle table/empty-label visibility to match."""
        self.table.rows = rows
        self.table.update()
        has_rows = bool(rows)
        self.table.set_visibility(has_rows)
        self.empty_label.set_visibility(not has_rows)


def empty_aware_table(
    columns: list[dict],
    *,
    row_key: str,
    pagination: dict | None = None,
    empty_text: str = DEFAULT_EMPTY_TEXT,
) -> EmptyAwareTable:
    """Build the table + label pair; call `.set_rows(...)` from your filter refresh."""
    table = ui.table(
        columns=columns, rows=[], row_key=row_key, pagination=pagination or {},
    ).classes("w-full")
    empty_label = ui.label(empty_text).classes("t-status t-muted")  # with the kit theme: as layout.empty()
    empty_label.set_visibility(False)
    return EmptyAwareTable(table=table, empty_label=empty_label)
