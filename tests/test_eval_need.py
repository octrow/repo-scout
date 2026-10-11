import re
import tomllib
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
SETS = sorted(EVAL_DIR.glob("*.toml"))
MAX_NEED_LEN = 400
MIN_PART_LEN = 4
# Repo-name parts that are ordinary English words: a need may legitimately use them.
GENERIC_PARTS = {
    "friends",  # JacobEvelyn/friends: plain word, not a product mention
    "actual",  # actualbudget/actual: plain word
}


def _hits(text: str, name: str) -> bool:
    pattern = rf"(?<![\w]){re.escape(name)}(?![\w])"
    return re.search(pattern, text, re.IGNORECASE) is not None


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_need_present_and_leak_free(path):
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    need = data.get("need", "")
    assert need.strip(), "need is empty"
    assert len(need) <= MAX_NEED_LEN
    for item in data["expected"]:
        full = item["repo"]
        owner, _, part = full.partition("/")
        assert not _hits(need, full), f"need leaks {full}"
        if len(part) >= MIN_PART_LEN and part.lower() not in GENERIC_PARTS:
            assert not _hits(need, part), f"need leaks {part}"


def test_sets_found():
    assert len(SETS) == 8
