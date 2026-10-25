"""Repository rules the linters don't check."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Built from parts, so this file doesn't contain the markers it looks for.
MARKERS = ("no" + "qa", "type" + ": ignore", "pyright" + ": ignore")


def test_no_suppression_comments():
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for folder in ("ironsworn_tui", "tests")
        for path in sorted((ROOT / folder).rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if any(marker in line for marker in MARKERS)
    ]
    assert found == [], "fix the finding instead of suppressing it"
