# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import math

from field_telemetry_analyzer.generate import generate

SEED = 20261110


def test_fault_injections() -> None:
    log, events = generate("standard", SEED)
    by_id = {e.id: e for e in events}
    assert len(events) == 8
    imu = log.imu
    assert imu[1200].ax - imu[1199].ax > 0.35
    nan_count = sum(
        1 for s in imu[2200:2250] if not math.isfinite(s.gx)
    )
    assert nan_count == 50
    f3 = by_id["F3"]
    assert f3.held_gz is not None
    for s in imu[int(36.0 / 0.01) : int(37.5 / 0.01)]:
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
        a = act[seq]
        if 1300 <= seq < 1350 and 26.0 <= seq * 0.02 < 27.0:
            assert a.left_cmd == 1.20 and a.left_meas == 1.00
    clean, _ = generate("clean", SEED)
    clean_x = {p.seq: p.x for p in clean.pose}
    for seq in range(2100, 2110):
        p = next(x for x in log.pose if x.seq == seq)
        assert abs(p.x - clean_x[seq] - 0.80) < 1e-9
    assert imu[5999].t - 59.99 > 0.23
    assert abs(imu[5999].t - 59.99 - 0.24) < 0.001
