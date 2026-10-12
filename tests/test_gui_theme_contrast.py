"""AA contrast of vendored theme (ported from nicegui-kit tests)."""
from pathlib import Path

import pytest

from repo_scout.gui.kit import theme


def test_font_ships_with_the_package() -> None:
    assert theme.FONT_FILE.is_file()
    assert (Path(theme.FONT_DIR) / "LICENSE.txt").is_file()


def test_contrast_formula_matches_wcag_extremes() -> None:
    assert theme.contrast("#000000", "#FFFFFF") > 20.9
    assert theme.contrast("#777777", "#777777") == 1


def test_both_themes_define_the_same_tokens() -> None:
    assert theme.TOKENS["dark"].keys() == theme.TOKENS["light"].keys()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_text_pair_reads_at_aa_in_both_themes(mode: str) -> None:
    tokens = theme.TOKENS[mode]
    weak = [(fg, bg, round(theme.contrast(tokens[fg], tokens[bg]), 2))
            for fg, bg in theme.TEXT_PAIRS if theme.contrast(tokens[fg], tokens[bg]) < 4.5]
    assert not weak
