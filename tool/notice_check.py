# SPDX-License-Identifier: Apache-2.0
"""Validate NOTICE against lockfile package inventory."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICE = ROOT / "NOTICE"
REQ_LOCK = ROOT / "requirements.lock.txt"
DEV_LOCK = ROOT / "requirements-dev.lock.txt"
PKG_LOCK = ROOT / "package-lock.json"


def dist_names_from_pip_lock(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    names: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^ \\+]+)", line)
        if m:
            names[m.group(1).lower()] = m.group(2)
    return names


def dist_names_from_pkg_lock(path: Path) -> dict[str, str]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for dep in ("@playwright/test", "http-server"):
        key = f"node_modules/{dep}"
        if key in data.get("packages", {}):
            out[dep] = data["packages"][key]["version"]
    return out


def main() -> int:
    notice = NOTICE.read_text(encoding="utf-8")
    if "REFERENCES.md" not in notice:
        raise SystemExit("NOTICE must reference REFERENCES.md")
    if "field-telemetry-analyzer, Copyright 2026 Arpan Bom" not in notice:
        raise SystemExit("NOTICE missing copyright line")
    combined = dist_names_from_pip_lock(REQ_LOCK)
    combined.update(dist_names_from_pip_lock(DEV_LOCK))
    combined.update(dist_names_from_pkg_lock(PKG_LOCK))
    for name, ver in combined.items():
        if not re.search(rf"{re.escape(name)}[^\n]*\b{re.escape(ver)}\b", notice, re.IGNORECASE):
            raise SystemExit(f"NOTICE missing {name}=={ver}")
        block_m = re.search(
            rf"(?:^|\n).*{re.escape(name)}[^\n]*{re.escape(ver)}[^\n]*\n(?:[^\n]*\n)?",
            notice,
            re.IGNORECASE,
        )
        block = block_m.group(0) if block_m else ""
        if "license" not in block.lower():
            raise SystemExit(f"NOTICE blank license for {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
