"""Index page (`/index`): Index repositories, Verdicts, renaming, and 'forget'."""
import re

from nicegui import ui

from ..index import Index
from . import runs_logic as rl
from . import shell
from .i18n import localize_table, t
from .kit import layout, table
from .verdict_dialog import DB_ERRORS, VerdictDialog, notify_db_error, open_index, readme_view

REPO_RE = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", re.ASCII)
ALL_PROJECTS = "All projects"
README_SLOT = """<q-td :props="props"><q-icon v-if="props.value" name="description" size="xs" class="t-muted"
:aria-label="props.col.yes" /><span v-else>—</span></q-td>"""
COLUMNS = [
    {"name": "name", "label": "Repo", "field": "name", "align": "left", "sortable": True},
    {"name": "desc", "label": "Description", "field": "desc", "align": "left"},
    {"name": "stars", "label": "★", "field": "stars", "align": "right", "sortable": True},
    {"name": "lang", "label": "Language", "field": "lang", "align": "left"},
    {"name": "date", "label": "Added", "field": "date", "align": "left", "sortable": True},
    {"name": "readme", "label": "README", "field": "readme", "align": "center"},
    {"name": "seen", "label": "Verdicts", "field": "seen", "align": "left"},
]


def check_repo(value: str) -> str | None:
    """Error for owner/repo format or None."""
    v = (value or "").strip()
    if not REPO_RE.fullmatch(v) or v.split("/")[1] in (".", ".."):
        return t("Use the owner/repo format")
    return None


def index_rows(idx: Index, *, project: str = "", kind: str = "", text: str = "") -> list[dict]:
    """Table rows: Index repos matching project, Verdict kind, and text filters."""
    verdicts = idx.verdicts(project or None)
    prefix = rl.VERDICT_PREFIX.get(kind, "")
    allowed = {v[1] for v in verdicts if v[2].startswith(prefix)} if (project or prefix) else None
    all_rows = idx.rows()
    seen = idx.seen([r["name"] for r in all_rows])
    needle = text.strip().lower()
    out = []
    for r in all_rows:
        m = r["meta"]
        if allowed is not None and r["key"] not in allowed:
            continue
        if needle and needle not in f"{r['name']} {m.get('desc', '')} {m.get('lang', '')}".lower():
            continue
        out.append({"key": r["key"], "name": r["name"], "desc": rl.plain_desc(m.get("desc")),
                    "stars": m.get("stars"), "lang": m.get("lang") or "—", "date": (r["fetched_at"] or "")[:10],
                    "readme": bool(r["has_readme"]), "seen": seen.get(r["key"], "—"),
                    "url": m.get("url") or f"https://github.com/{r['name']}"})
    return out


class IndexPage:
    def __init__(self) -> None:
        self.flt = {"project": "", "kind": "", "text": ""}
        self.rows: dict[str, dict] = {}
        self.verdicts = VerdictDialog(lambda _: self.refresh())
        self.panel, self.confirm = ui.dialog(), ui.dialog()
        self.table: table.EmptyAwareTable | None = None
        self.count: ui.label | None = None

    def refresh(self) -> None:
        try:
            with open_index() as idx:
                rows = index_rows(idx, **self.flt)
                total = len(idx.rows())
        except DB_ERRORS:
            notify_db_error("Failed to read Index for Index page")
            return
        self.rows = {r["key"]: r for r in rows}
        # Verdicts column only once some shown repo has one
        has_seen = any(r["seen"] != "—" for r in rows)
        self.table.table.columns = [{**c, "label": t(c["label"]), "yes": t("yes")}  # type: ignore[union-attr]
                                    for c in COLUMNS if c["name"] != "seen" or has_seen]
        self.table.set_rows(rows)  # type: ignore[union-attr]
        self.count.set_text(t("Showing {shown} of {total}").format(shown=len(rows), total=total))  # type: ignore[union-attr]

    def set_filter(self, key: str, value: str | None) -> None:
        self.flt[key] = value or ""
        if key == "project" and value == ALL_PROJECTS:
            self.flt[key] = ""
        self.refresh()

    def filters(self) -> None:
        with open_index() as idx:
            projects = list(dict.fromkeys(v[0] for v in idx.verdicts()))
        with layout.filter_bar():
            layout.search_field(t("Search by repo and description"), on_change=lambda e: self.set_filter("text", e.value))
            ui.select({ALL_PROJECTS: t(ALL_PROJECTS), **{p: p for p in projects}}, value=ALL_PROJECTS,
                      on_change=lambda e: self.set_filter("project", e.value)) \
                .props(f'outlined dense aria-label="{t("Project")}"')
            ui.select(rl.verdict_filter_options(), value="",
                      on_change=lambda e: self.set_filter("kind", e.value)).props(f'outlined dense aria-label="{t("Verdict")}"')
            ui.space()
            self.count = ui.label().classes("t-meta")

    def open_panel(self, key: str) -> None:
        row = self.rows[key]
        self.panel.clear()
        with self.panel, layout.section_card().style(shell.PANEL_STYLE):
            with ui.row().classes("ic-split w-full items-start flex-nowrap"):
                layout.heading(row["name"], level=2).classes("min-w-0")
                ui.button(icon="close", on_click=self.panel.close) \
                    .props(f'flat round dense aria-label="{t("Close")}"').classes("shrink-0")
            ui.link(t("Open on GitHub"), row["url"], new_tab=True)
            ui.label(row["desc"]).classes("t-meta")
            ui.label(t("Verdicts: {seen}").format(seen=row["seen"]))
            ui.separator()
            readme_view(row["name"])
            # one row: rare and destructive actions on the left, the everyday ones on the right
            with layout.actions_row(end=False):
                layout.button(t("Forget"), kind="danger", on_click=lambda: self.forget_dialog(row["name"]))
                layout.button(t("Rename"), kind="quiet", icon="edit", on_click=lambda: self.rename_dialog(row["name"]))
                ui.space()
                layout.button(t("Close"), kind="quiet", on_click=self.panel.close)
                layout.button(t("Set verdict"), kind="primary", icon="rate_review",
                              on_click=lambda: self.verdicts.open(row["name"]))
        self.panel.open()

    def rename_dialog(self, name: str) -> None:
        self.confirm.clear()
        with self.confirm, layout.section_card():
            layout.heading(t("Rename repo"), level=2)
            ui.label(t("Old record will be removed from Index; verdicts will move to the new name.")).classes("t-meta")
            new = layout.field(t("New name"), value=name, hint="owner/repo", validation={
                t("Use the owner/repo format"): lambda v: check_repo(v) is None})

            def apply() -> None:
                if not new.validate():
                    return
                try:
                    with open_index() as idx:
                        idx.rename(name, new.value.strip())
                except DB_ERRORS:
                    notify_db_error(f"Failed to rename: {name}")
                    return
                self.confirm.close()
                self.panel.close()
                ui.notify(t("Renamed: {name}").format(name=new.value.strip()), type="positive")
                self.refresh()

            with layout.actions_row():
                layout.button(t("Cancel"), kind="quiet", on_click=self.confirm.close)
                layout.button(t("Rename"), kind="primary", on_click=apply)
        self.confirm.open()

    def forget_dialog(self, name: str) -> None:
        self.confirm.clear()
        with self.confirm, layout.section_card():
            layout.heading(t("Forget repo?"), level=2)
            ui.label(t("{name} leaves Index search. Its verdicts stay.").format(name=name)).classes("t-meta")

            def forget() -> None:
                try:
                    with open_index() as idx:
                        idx.forget(name)
                except DB_ERRORS:
                    notify_db_error(f"Failed to delete from Index: {name}")
                    return
                self.confirm.close()
                self.panel.close()
                self.refresh()

            with layout.actions_row():
                layout.button(t("Cancel"), kind="quiet", on_click=self.confirm.close)
                layout.button(t("Forget"), kind="danger", on_click=forget)
        self.confirm.open()

    def build(self) -> None:
        self.filters()
        columns = [{**c, "label": t(c["label"])} for c in COLUMNS]
        self.table = table.empty_aware_table(columns, row_key="key", pagination={"rowsPerPage": 25},
                                             empty_text=t("No repos in the Index yet. Run a search to add them."))
        self.table.table.add_slot("body-cell-readme", README_SLOT)
        localize_table(self.table.table)
        self.table.table.on("rowClick", lambda e: self.open_panel(e.args[1]["key"]))
        self.refresh()


def index_page() -> None:
    shell.shell("/index")
    with layout.page_container(max_width=shell.PAGE_WIDTH):
        layout.heading(t("Index"), level=1)
        IndexPage().build()


def register() -> None:
    ui.page("/index")(index_page)
