# SPDX-License-Identifier: Apache-2.0
"""Fail if authored files lack the Apache-2.0 SPDX header."""
from __future__ import annotations

from pathlib import Path

MARKER = "SPDX-License-Identifier: Apache-2.0"
ROOT = Path(__file__).resolve().parents[1]
GLOBS = (
    "field_telemetry_analyzer/**/*.py",
    "tool/*.py",
    "tool/*.sh",
    ".github/workflows/*.yml",
    "field_telemetry_analyzer/templates/*.j2",
)


def _check(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 0
    if lines and lines[0].startswith("#!"):
        start = 1
    head = "\n".join(lines[start : start + 3])
    if MARKER not in head:
        raise SystemExit(f"missing SPDX in {path}")


def main() -> int:
    for pattern in GLOBS:
        for path in ROOT.glob(pattern):
            _check(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
