# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORTS = (
    "mqtt",
    "sqlalchemy",
    "psycopg",
    "grafana",
    "pandas",
    "scipy",
    "sklearn",
    "rclpy",
    "mcap",
)

FORBIDDEN_TEST = ("pytest.skip", "pytest.xfail", "assert True")
FORBIDDEN_INVENTED = re.compile(r"\binvented\b", re.IGNORECASE)

ALLOW_INVENTED = (
    'Never "invented."',
    "wording ban on `invented`",
    "forbids the word",
)


def test_license_bytes() -> None:
    data = (ROOT / "LICENSE").read_bytes()
    assert len(data) == 11358
    assert (
        hashlib.sha256(data).hexdigest()
        == "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    )


def test_scope_guards() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "original implementation, inspired by" in readme
    assert "synthetic" in readme.lower()
    for path in (ROOT / "field_telemetry_analyzer").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for bad in FORBIDDEN_IMPORTS:
            assert f"import {bad}" not in text
            assert f"from {bad}" not in text
    for path in (ROOT / "tests").rglob("*.py"):
        if path.name == "test_guards.py":
            continue
        text = path.read_text(encoding="utf-8")
        for bad in FORBIDDEN_TEST:
            assert bad not in text
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "continue-on-error" not in text
        assert not re.search(r"run:\s*echo\s+['\"]?ok", text)
    pages = ROOT / ".github" / "workflows" / "pages.yml"
    assert pages.is_file()
    pt = pages.read_text(encoding="utf-8")
    assert "workflow_run" in pt
    assert "branches: [main]" in pt or "branches:\n      - main" in pt
    assert "permissions:" in pt
    skip_md = {ROOT / "PLAN.md", ROOT / "TASKS.md"}
    for path in [p for p in ROOT.rglob("*.md") if p not in skip_md] + list(
        (ROOT / "field_telemetry_analyzer").rglob("*.py")
    ):
        text = path.read_text(encoding="utf-8")
        for m in FORBIDDEN_INVENTED.finditer(text):
            snippet = text[max(0, m.start() - 40) : m.end() + 40]
            if not any(a in snippet for a in ALLOW_INVENTED):
                raise AssertionError(f"forbidden invented in {path}: {snippet!r}")
