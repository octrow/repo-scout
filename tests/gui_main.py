"""Главный файл для nicegui.testing.User: регистрирует страницы без ui.run."""
from nicegui import ui

from repo_scout.gui import app
from repo_scout.gui.kit import theme

theme.apply_theme()
app.register_pages()

ui.run()
