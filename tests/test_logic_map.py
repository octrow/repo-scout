"""docs/logic-map.md `Module:` lines name functions that exist."""
import importlib
import re
from functools import reduce
from pathlib import Path

MAP = Path(__file__).parent.parent / "docs" / "logic-map.md"


def test_module_lines_point_to_existing_functions():
    refs = [ref.strip() for line in MAP.read_text().splitlines() if line.startswith("Module:")
            for ref in line.removeprefix("Module:").split(",")]
    assert refs
    for ref in refs:
        path, _, attr = ref.partition("::")
        module = importlib.import_module(re.sub(r"\.py$", "", path).replace("/", "."))
        assert reduce(getattr, attr.split("."), module), ref
