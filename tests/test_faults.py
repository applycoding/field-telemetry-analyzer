# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from field_telemetry_analyzer.generate import generate, write_run

SEED = 20261110

EXPECTED_EVENTS = [
    ("F1", "imu_bias", "imu", 12.0, 60.0, 0.40, "m/s^2"),
    ("F2", "gyro_dropout", "imu", 22.0, 22.50, 50.0, "samples"),
    ("F3", "stuck_sensor", "imu", 36.0, 37.50, 1.50, "s"),
    ("F4", "timestamp_gap", "pose", 18.0, 18.40, 0.42, "s"),
    ("F5", "timestamp_jump", "pose", 45.0, 45.0, -0.25, "s"),
    ("F6", "actuator_sat", "actuator", 26.0, 27.0, 1.20, "m/s"),
    ("F7", "pose_jump", "pose", 42.0, 42.20, 0.80, "m"),
    ("F8", "clock_drift", "imu", 48.0, 60.0, 0.02, "rho"),
]


def test_fault_injections() -> None:
    log, events = generate("standard", SEED)
    clean, _ = generate("clean", SEED)
    by_id = {e.id: e for e in events}
    assert len(events) == 8
    imu = log.imu
    imu_c = clean.imu
    for k in range(1200, 6000):
        assert abs((imu[k].ax - imu_c[k].ax) - 0.40) < 1e-12
    nan_count = sum(1 for s in imu[2200:2250] if not math.isfinite(s.gx))
    assert nan_count == 50
    f3 = by_id["F3"]
    assert f3.held_gz is not None
    for s in imu[3600:3750]:
        assert s.gz == f3.held_gz
    assert imu[3599].gz != f3.held_gz
    pose_seqs = {p.seq for p in log.pose}
    assert all(seq not in pose_seqs for seq in range(900, 920))
    gap = next(p for p in log.pose if p.seq == 920)
    assert abs(gap.t - 17.98 - 0.42) < 1e-6
    jmp = next(p for p in log.pose if p.seq == 2250)
    assert abs(jmp.t - 44.75) < 1e-9
    act = {a.seq: a for a in log.actuator}
    for seq in range(1300, 1350):
        if 26.0 <= seq * 0.02 < 27.0:
            a = act[seq]
            assert a.left_cmd == 1.20 and a.left_meas == 1.00
    clean_x = {p.seq: p.x for p in clean.pose}
    for seq in range(2100, 2110):
        p = next(x for x in log.pose if x.seq == seq)
        assert abs(p.x - clean_x[seq] - 0.80) < 1e-9
    snap = next(p for p in log.pose if p.seq == 2110)
    assert snap.x == clean_x[2110]
    t5999_us = 48_000_000 + (59_990_000 - 48_000_000) * 102 // 100
    assert abs(imu[5999].t - t5999_us / 1e6) < 1e-9
    assert abs(imu[5999].t - 60.2298) < 1e-4

    with tempfile.TemporaryDirectory() as d:
        write_run(log, events, d)
        sidecar = json.loads(Path(d, "ground_truth.json").read_text(encoding="utf-8"))
        assert len(sidecar) == 8
        for exp in EXPECTED_EVENTS:
            row = next(r for r in sidecar if r["id"] == exp[0])
            assert row["detector"] == exp[1]
            assert row["stream"] == exp[2]
            assert row["t_start"] == exp[3]
            assert row["t_end"] == exp[4]
            assert row["magnitude"] == exp[5]
            assert row["unit"] == exp[6]
