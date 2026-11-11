# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from field_telemetry_analyzer.detect import detect
from field_telemetry_analyzer.generate import generate
from field_telemetry_analyzer.score import score, write_score

SEED = 20261110
FLAGS_SHA = "ca6883f6728a58c86066a63c69b9f1073b57a123958740fe4cd6d3d696dd15b1"
SCORE_SHA = "9c9de2143fa57534de0a1b29966a77102b3c21835af21bd441fc0c7f46a2cb53"


def test_flags_and_score_sha256() -> None:
    log, events = generate("standard", SEED)
    flags = detect(log)
    sc = score(flags, events)
    with tempfile.TemporaryDirectory() as d:
        outp = Path(d)
        write_score(sc, outp / "score.json")
        from field_telemetry_analyzer.report import _write_flags_csv

        _write_flags_csv(outp / "flags.csv", flags)
        assert hashlib.sha256((outp / "flags.csv").read_bytes()).hexdigest() == FLAGS_SHA
        assert hashlib.sha256((outp / "score.json").read_bytes()).hexdigest() == SCORE_SHA
