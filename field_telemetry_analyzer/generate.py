# SPDX-License-Identifier: Apache-2.0
"""Seeded synthetic log generator with eight documented fault injections."""
from __future__ import annotations

import json
import math
import os
from typing import Literal

import numpy as np

from field_telemetry_analyzer.kinematics import (
    integrate_pose_100hz,
    specific_force_at,
    velocity_omega,
    wheel_speeds,
)
from field_telemetry_analyzer.models import (
    ActuatorSample,
    Event,
    ImuSample,
    PoseSample,
    RunLog,
)


def _imu_stamp_us(seq: int, *, apply_drift: bool) -> int:
    t_true_us = seq * 10000
    if apply_drift and t_true_us >= 48_000_000:
        return 48_000_000 + (t_true_us - 48_000_000) * 102 // 100
    return t_true_us


def generate(
    scenario: Literal["standard", "clean"], seed: int
) -> tuple[RunLog, tuple[Event, ...]]:
    apply_drift = scenario == "standard"
    rng = np.random.Generator(np.random.PCG64(seed))
    xs, ys, yaws = integrate_pose_100hz()
    imu: list[ImuSample] = []
    pose: list[PoseSample] = []
    actuator: list[ActuatorSample] = []

    for k in range(6000):
        t_true = k * 0.01
        v, omega = velocity_omega(t_true)
        ax, ay, az, gx, gy, gz = specific_force_at(t_true, v, omega)
        n_ax = ax + rng.normal(0.0, 0.02)
        n_ay = ay + rng.normal(0.0, 0.02)
        n_az = az + rng.normal(0.0, 0.02)
        n_gx = gx + rng.normal(0.0, 0.005)
        n_gy = gy + rng.normal(0.0, 0.005)
        n_gz = gz + rng.normal(0.0, 0.005)
        imu.append(
            ImuSample(
                t=_imu_stamp_us(k, apply_drift=apply_drift) / 1e6,
                seq=k,
                ax=n_ax,
                ay=n_ay,
                az=n_az,
                gx=n_gx,
                gy=n_gy,
                gz=n_gz,
            )
        )

    for k in range(3000):
        t_host = k * 0.02
        ik = k * 2
        n_x = xs[ik] + rng.normal(0.0, 0.005)
        n_y = ys[ik] + rng.normal(0.0, 0.005)
        n_yaw = yaws[ik] + rng.normal(0.0, 0.002)
        pose.append(
            PoseSample(
                t=t_host,
                seq=k,
                x=n_x,
                y=n_y,
                yaw=n_yaw,
            )
        )

    for k in range(3000):
        t_host = k * 0.02
        ik = k * 2
        t_true = ik * 0.01
        v, omega = velocity_omega(t_true)
        u_l, u_r = wheel_speeds(v, omega)
        lc = u_l
        rc = u_r
        lm = u_l + rng.normal(0.0, 0.01)
        rm = u_r + rng.normal(0.0, 0.01)
        actuator.append(
            ActuatorSample(
                t=t_host,
                seq=k,
                left_cmd=lc,
                right_cmd=rc,
                left_meas=lm,
                right_meas=rm,
            )
        )

    events: list[Event] = []
    if scenario == "standard":
        _apply_injections(imu, pose, actuator, events)

    log = RunLog(
        imu=tuple(imu),
        pose=tuple(pose),
        actuator=tuple(actuator),
    )
    return log, tuple(events)


def _apply_injections(
    imu: list[ImuSample],
    pose: list[PoseSample],
    actuator: list[ActuatorSample],
    events: list[Event],
) -> None:
    # F1 imu_bias
    for k in range(1200, 6000):
        s = imu[k]
        imu[k] = ImuSample(s.t, s.seq, s.ax + 0.40, s.ay, s.az, s.gx, s.gy, s.gz)
    events.append(
        Event("F1", "imu_bias", "imu", 12.0, 60.0, 0.40, "m/s^2")
    )

    # F2 gyro_dropout [22, 22.5)
    for k in range(2200, 2250):
        s = imu[k]
        t_us = _imu_stamp_us(k, apply_drift=True)
        imu[k] = ImuSample(t_us / 1e6, s.seq, s.ax, s.ay, s.az, float("nan"), float("nan"), float("nan"))
    events.append(
        Event("F2", "gyro_dropout", "imu", 22.0, 22.50, 50.0, "samples")
    )

    # F3 stuck_sensor — hold noiseless gz at kinematic value
    held_gz = 0.50
    seq_3599 = 3599
    if abs(imu[seq_3599].gz - held_gz) < 1e-12:
        held_gz = 0.51
    t_hold_start = 36.0
    t_hold_end = 37.50
    for k in range(int(t_hold_start / 0.01), int(t_hold_end / 0.01)):
        s = imu[k]
        t_us = _imu_stamp_us(k, apply_drift=True)
        imu[k] = ImuSample(t_us / 1e6, s.seq, s.ax, s.ay, s.az, s.gx, s.gy, held_gz)
    events.append(
        Event("F3", "stuck_sensor", "imu", 36.0, 37.50, 1.50, "s", held_gz=held_gz)
    )

    # F4 timestamp_gap — drop pose seq 900..919 (host 18.00 not written)
    drop_lo, drop_hi = 900, 920
    new_pose: list[PoseSample] = []
    for p in pose:
        if drop_lo <= p.seq < drop_hi:
            continue
        new_pose.append(p)
    pose[:] = new_pose
    events.append(
        Event("F4", "timestamp_gap", "pose", 18.0, 18.40, 0.42, "s")
    )

    # F5 timestamp_jump seq 2250 -> 44.75
    for i, p in enumerate(pose):
        if p.seq == 2250:
            pose[i] = PoseSample(44.75, p.seq, p.x, p.y, p.yaw)
            break
    events.append(
        Event("F5", "timestamp_jump", "pose", 45.0, 45.0, -0.25, "s")
    )

    # F6 actuator_sat [26, 27)
    for k in range(1300, 1350):
        s = actuator[k]
        actuator[k] = ActuatorSample(
            s.t, s.seq, 1.20, s.right_cmd, 1.00, s.right_meas
        )
    events.append(
        Event("F6", "actuator_sat", "actuator", 26.0, 27.0, 1.20, "m/s")
    )

    # F7 pose_jump [42, 42.2) +0.80 on x
    for i, p in enumerate(pose):
        if 2100 <= p.seq < 2110:
            pose[i] = PoseSample(p.t, p.seq, p.x + 0.80, p.y, p.yaw)
    events.append(
        Event("F7", "pose_jump", "pose", 42.0, 42.20, 0.80, "m")
    )

    # F8 clock_drift — stamps already via _imu_stamp_us when refreshed
    for k in range(6000):
        t_us = _imu_stamp_us(k, apply_drift=True)
        s = imu[k]
        imu[k] = ImuSample(
            t_us / 1e6,
            s.seq,
            s.ax,
            s.ay,
            s.az,
            s.gx,
            s.gy,
            s.gz,
        )
    events.append(
        Event("F8", "clock_drift", "imu", 48.0, 60.0, 0.02, "rho")
    )


def write_run(log: RunLog, events: tuple[Event, ...], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    _write_imu_csv(os.path.join(out_dir, "imu.csv"), log.imu)
    _write_pose_csv(os.path.join(out_dir, "pose.csv"), log.pose)
    _write_actuator_csv(os.path.join(out_dir, "actuator.csv"), log.actuator)
    _write_jsonl(os.path.join(out_dir, "log.jsonl"), log)
    if events:
        _write_ground_truth(os.path.join(out_dir, "ground_truth.json"), events)


def _fmt_ts_us(t: float) -> str:
    us = round(t * 1e6)
    return f"{us / 1e6:.6f}"


def _fmt_float(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return format(x, ".17g")


def _write_imu_csv(path: str, samples: tuple[ImuSample, ...]) -> None:
    lines = ["t,seq,ax,ay,az,gx,gy,gz"]
    for s in samples:
        lines.append(
            ",".join(
                [
                    _fmt_ts_us(s.t),
                    str(s.seq),
                    _fmt_float(s.ax),
                    _fmt_float(s.ay),
                    _fmt_float(s.az),
                    _fmt_float(s.gx),
                    _fmt_float(s.gy),
                    _fmt_float(s.gz),
                ]
            )
        )
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _write_pose_csv(path: str, samples: tuple[PoseSample, ...]) -> None:
    lines = ["t,seq,x,y,yaw"]
    for s in samples:
        lines.append(
            ",".join(
                [
                    _fmt_ts_us(s.t),
                    str(s.seq),
                    _fmt_float(s.x),
                    _fmt_float(s.y),
                    _fmt_float(s.yaw),
                ]
            )
        )
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _write_actuator_csv(path: str, samples: tuple[ActuatorSample, ...]) -> None:
    lines = ["t,seq,left_cmd,right_cmd,left_meas,right_meas"]
    for s in samples:
        lines.append(
            ",".join(
                [
                    _fmt_ts_us(s.t),
                    str(s.seq),
                    _fmt_float(s.left_cmd),
                    _fmt_float(s.right_cmd),
                    _fmt_float(s.left_meas),
                    _fmt_float(s.right_meas),
                ]
            )
        )
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _write_jsonl(path: str, log: RunLog) -> None:
    records: list[tuple[float, int, dict]] = []
    for s in log.imu:
        records.append(
            (
                s.seq * 0.01,
                0,
                {
                    "t": s.t,
                    "seq": s.seq,
                    "topic": "/imu/data",
                    "type": "Imu",
                    "data": {
                        "ax": s.ax,
                        "ay": s.ay,
                        "az": s.az,
                        "gx": s.gx,
                        "gy": s.gy,
                        "gz": s.gz,
                    },
                },
            )
        )
    for s in log.pose:
        records.append(
            (
                s.seq * 0.02,
                1,
                {
                    "t": s.t,
                    "seq": s.seq,
                    "topic": "/pose",
                    "type": "Pose",
                    "data": {"x": s.x, "y": s.y, "yaw": s.yaw},
                },
            )
        )
    for s in log.actuator:
        records.append(
            (
                s.seq * 0.02,
                2,
                {
                    "t": s.t,
                    "seq": s.seq,
                    "topic": "/actuator",
                    "type": "Actuator",
                    "data": {
                        "left_cmd": s.left_cmd,
                        "right_cmd": s.right_cmd,
                        "left_meas": s.left_meas,
                        "right_meas": s.right_meas,
                    },
                },
            )
        )
    records.sort(key=lambda r: (r[0], r[1]))
    with open(path, "w", newline="\n") as f:
        f.writelines(json.dumps(obj, allow_nan=True) + "\n" for _, _, obj in records)


def _write_ground_truth(path: str, events: tuple[Event, ...]) -> None:
    out = []
    for e in events:
        item = {
            "id": e.id,
            "detector": e.detector,
            "stream": e.stream,
            "t_start": e.t_start,
            "t_end": e.t_end,
            "magnitude": e.magnitude,
            "unit": e.unit,
        }
        if e.held_gz is not None:
            item["held_gz"] = e.held_gz
        out.append(item)
    with open(path, "w", newline="\n") as f:
        json.dump(out, f, indent=2, allow_nan=False)
        f.write("\n")
