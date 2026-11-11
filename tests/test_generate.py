# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path

from field_telemetry_analyzer.generate import generate, write_run

SEED = 20261110


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
    for k in range(6000):
        a, b = log_s.imu[k], log_c.imu[k]
        if k < 1200:
            assert a == b
            continue
        assert a.ax == b.ax + 0.40
        if 2200 <= k < 2250:
            assert not math.isfinite(a.gx) and math.isfinite(b.gx)
            assert not math.isfinite(a.gy) and not math.isfinite(a.gz)
            assert a.ay == b.ay and a.az == b.az and a.t == b.t
            continue
        if 3600 <= k < 3750:
            assert abs(a.gz - 0.50) < 1e-9 or abs(a.gz - 0.51) < 1e-9
            assert a.ay == b.ay and a.az == b.az and a.gx == b.gx and a.gy == b.gy and a.t == b.t
            continue
        if k >= 4801:
            assert a.t != b.t
        if k >= 4800:
            assert a.ay == b.ay and a.az == b.az and a.gx == b.gx and a.gy == b.gy and a.gz == b.gz
            if k < 4801:
                assert a.t == b.t
            continue
        assert a.ay == b.ay and a.az == b.az and a.gx == b.gx and a.gy == b.gy and a.gz == b.gz and a.t == b.t
    clean_pose = {p.seq: p for p in log_c.pose}
    for p in log_s.pose:
        cp = clean_pose[p.seq]
        if 2100 <= p.seq < 2110:
            assert p.x == cp.x + 0.80 and p.y == cp.y and p.yaw == cp.yaw and p.t == cp.t
        elif p.seq == 2250:
            assert p.t == 44.75 and p.x == cp.x and p.y == cp.y and p.yaw == cp.yaw
        else:
            assert p == cp
    clean_act = {a.seq: a for a in log_c.actuator}
    for a in log_s.actuator:
        ca = clean_act[a.seq]
        if 1300 <= a.seq < 1350 and 26.0 <= a.seq * 0.02 < 27.0:
            assert a.left_cmd == 1.20 and a.left_meas == 1.00
            assert a.right_cmd == ca.right_cmd and a.right_meas == ca.right_meas and a.t == ca.t
        else:
            assert a == ca
    for pc in log_c.pose:
        if 900 <= pc.seq < 920:
            assert pc.seq not in {p.seq for p in log_s.pose}


def test_no_wall_clock() -> None:
    root = Path(__file__).resolve().parents[1] / "field_telemetry_analyzer"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "time.time" not in text
        assert "time.time_ns" not in text
