# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from field_telemetry_analyzer.detect import detect
from field_telemetry_analyzer.score import score, write_score


def test_score_json_stable(standard_log) -> None:
    log, events = standard_log
    flags = detect(log)
    sc = score(flags, events)
    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        write_score(sc, f.name)
        data = json.loads(Path(f.name).read_text(encoding="utf-8"))
    assert data["metric"] == "event_attribution_v1"
    assert data["tp"] == 8
    assert data["fp"] == 0
    assert data["fn"] == 0


