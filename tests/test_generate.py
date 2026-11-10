# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from field_telemetry_analyzer.generate import generate, write_run

SEED = 20261110
DROP_POSE = set(range(900, 920))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generate_bit_identical() -> None:
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        write_run(*generate("standard", SEED), d1)
        write_run(*generate("standard", SEED), d2)
        for name in ("imu.csv", "pose.csv", "actuator.csv", "log.jsonl"):
            assert _sha(Path(d1) / name) == _sha(Path(d2) / name)
    with tempfile.TemporaryDirectory() as c1, tempfile.TemporaryDirectory() as c2:
        write_run(*generate("clean", SEED), c1)
        write_run(*generate("clean", SEED), c2)
        for name in ("imu.csv", "pose.csv", "actuator.csv", "log.jsonl"):
            assert _sha(Path(c1) / name) == _sha(Path(c2) / name)
    log_s, _ = generate("standard", SEED)
    log_c, _ = generate("clean", SEED)
    assert log_s.imu[0].ax != generate("standard", SEED + 1)[0].imu[0].ax
    by_seq_clean_pose = {p.seq: p for p in log_c.pose}
    for p in log_s.pose:
        pc = by_seq_clean_pose[p.seq]
        assert abs(p.x - pc.x) < 1e-12 or (2100 <= p.seq < 2110)
        assert abs(p.y - pc.y) < 1e-12
    for k in range(6000):
        a, b = log_s.imu[k], log_c.imu[k]
        if k < 1200:
            assert a.ax == b.ax
        if not (2200 <= k < 2250) and not (3600 <= k < 3750) and k < 4800 and k < 4800:
            assert a.t == b.t
    for pc in log_c.pose:
        if pc.seq in DROP_POSE:
            assert pc.seq not in {p.seq for p in log_s.pose}


def test_no_wall_clock() -> None:
    root = Path(__file__).resolve().parents[1] / "field_telemetry_analyzer"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "time.time" not in text
        assert "time.time_ns" not in text
