# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import math

from field_telemetry_analyzer.kinematics import integrate_pose_100hz, truth_pose_at, yaw_closed_form

SEED = 20261110


def test_kinematic_checkpoints() -> None:
    xs, ys, yaws = integrate_pose_100hz()
    for t, exp in (
        (8.0, truth_pose_at(8.0)),
        (16.0, truth_pose_at(16.0)),
        (20.0, truth_pose_at(20.0)),
        (36.0, truth_pose_at(36.0)),
        (48.0, truth_pose_at(48.0)),
    ):
        k = round(t / 0.01)
        assert abs(xs[k] - exp[0]) <= 1e-12
        assert abs(ys[k] - exp[1]) <= 1e-12
        assert abs(yaws[k] - exp[2]) <= 1e-12
    t50 = 50.0
    k = round(t50 / 0.01)
    _, _, yaws = integrate_pose_100hz()
    assert abs(yaws[k] - (5.60 + 1.2 / math.pi)) < 1e-12
    assert abs(yaw_closed_form(t50) - (5.60 + 1.2 / math.pi)) < 1e-12
