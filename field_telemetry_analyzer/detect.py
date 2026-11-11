# SPDX-License-Identifier: Apache-2.0
"""Deterministic explainable detectors (numpy only, no ML)."""
from __future__ import annotations

import math
from collections.abc import Collection

import numpy as np

from field_telemetry_analyzer.kinematics import U_MAX
from field_telemetry_analyzer.models import (
    ActuatorSample,
    ClockDriftWindow,
    Flag,
    ImuSample,
    PoseSample,
    RunLog,
)

IMU_BIAS_DELTA = 0.25
IMU_BIAS_BLOCK = 20
STUCK_VAR = 2.5e-7
STUCK_IMU_BLOCK = 30
GAP_TH = 0.10
SAT_DWELL_SAMPLES = 10
POSE_V_MAX = 0.80
DRIFT_ABS = 0.08
DRIFT_WINDOW_S = 5.0
DRIFT_STRIDE_S = 2.5
DRIFT_GRID_MIN_PAIRS = 10

ALL_DETECTORS = (
    "imu_bias",
    "gyro_dropout",
    "stuck_sensor",
    "timestamp_gap",
    "timestamp_jump",
    "actuator_sat",
    "pose_jump",
    "clock_drift",
)


def detect(log: RunLog, disable: Collection[str] = ()) -> list[Flag]:
    unknown = set(disable) - set(ALL_DETECTORS)
    if unknown:
        raise ValueError(f"unknown detector(s): {sorted(unknown)}")
    disabled = set(disable)
    flags: list[Flag] = []
    if "imu_bias" not in disabled:
        flags.extend(_detect_imu_bias(log.imu))
    if "gyro_dropout" not in disabled:
        flags.extend(detect_gyro_dropout(log.imu))
    if "stuck_sensor" not in disabled:
        flags.extend(_detect_stuck_sensor(log))
    if "timestamp_gap" not in disabled:
        flags.extend(_detect_timestamp_gap(log.pose))
    if "timestamp_jump" not in disabled:
        flags.extend(_detect_timestamp_jump(log.pose))
    if "actuator_sat" not in disabled:
        flags.extend(_detect_actuator_sat(log.actuator))
    if "pose_jump" not in disabled:
        flags.extend(_detect_pose_jump(log.pose))
    if "clock_drift" not in disabled:
        flags.extend(_detect_clock_drift(log))
    flags.sort(key=lambda f: (f.t_host, f.stream, f.detector, f.seq))
    return flags


def analyze_clock_drift_windows(log: RunLog) -> list[ClockDriftWindow]:
    pose = log.pose
    imu = log.imu
    rate_mids, rate_raw = _pose_yaw_rates(pose)
    if not rate_mids:
        return []
    smooth_rate = _smooth_pose_rates(rate_mids, rate_raw, 0.20)
    smooth_gz = _rolling_mean_imu_gz_seq(imu, IMU_BIAS_BLOCK)

    out: list[ClockDriftWindow] = []
    w_index = 1
    while True:
        t0 = DRIFT_STRIDE_S * w_index
        t1 = t0 + DRIFT_WINDOW_S
        if t1 > 60.0 + 1e-9:
            break
        imu_lo = w_index * int(DRIFT_STRIDE_S / 0.01)
        imu_hi = imu_lo + int(DRIFT_WINDOW_S / 0.01)
        win_mids: list[float] = []
        win_rates: list[float] = []
        for mid, sm in zip(rate_mids, smooth_rate, strict=True):
            if t0 <= mid < t1 and sm is not None:
                win_mids.append(mid)
                win_rates.append(sm)
        if len(win_mids) < 2:
            out.append(
                ClockDriftWindow(t1, imu_hi, None, False, None)
            )
            w_index += 1
            continue
        ptp = max(win_rates) - min(win_rates)
        if ptp < 0.20:
            out.append(ClockDriftWindow(t1, imu_hi, None, False, None))
            w_index += 1
            continue
        fit_t = np.array(win_mids, dtype=float)
        fit_r = np.array(win_rates, dtype=float)
        imu_idxs = [
            i
            for i in range(imu_lo, imu_hi)
            if 0 <= i < len(imu) and smooth_gz[i] is not None
        ]
        if not imu_idxs:
            out.append(ClockDriftWindow(t1, imu_hi, None, False, None))
            w_index += 1
            continue
        gz_arr = np.array([smooth_gz[i] for i in imu_idxs], dtype=float)
        stamp_arr = np.array([imu[i].t for i in imu_idxs], dtype=float)
        t_lo, t_hi = float(fit_t[0]), float(fit_t[-1])
        best_sse = float("inf")
        best_delta = 0.0
        any_valid = False
        for delta_i in range(-100, 101):
            delta = delta_i * 0.01
            t_q = stamp_arr - delta
            in_sup = (t_q >= t_lo) & (t_q <= t_hi) & _interp_pose_gap_ok(
                t_q, fit_t
            )
            n_pairs = int(in_sup.sum())
            if n_pairs < DRIFT_GRID_MIN_PAIRS:
                continue
            any_valid = True
            rate_v = np.interp(t_q[in_sup], fit_t, fit_r)
            sse = float(np.sum((gz_arr[in_sup] - rate_v) ** 2))
            if sse < best_sse - 1e-15:
                best_sse = sse
                best_delta = delta
            elif abs(sse - best_sse) <= 1e-12 and (
                abs(delta) < abs(best_delta)
                or (abs(delta) == abs(best_delta) and delta < best_delta)
            ):
                best_delta = delta
        identifiable = (
            any_valid
            and math.isfinite(best_sse)
            and abs(best_delta) < 1.0 - 1e-9
        )
        out.append(
            ClockDriftWindow(
                t_host_end=t1,
                imu_end_seq=imu_hi,
                delta=best_delta if identifiable else None,
                identifiable=identifiable,
                sse=best_sse if identifiable else None,
            )
        )
        w_index += 1
    return out


def _detect_imu_bias(imu: tuple[ImuSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    n = len(imu)
    for k in range(2, n // IMU_BIAS_BLOCK + 1):
        end_seq = k * IMU_BIAS_BLOCK
        if end_seq >= n:
            break
        trail_lo, trail_hi = end_seq - IMU_BIAS_BLOCK, end_seq
        lead_lo, lead_hi = end_seq - 2 * IMU_BIAS_BLOCK, end_seq - IMU_BIAS_BLOCK
        trail = [imu[s].ax for s in range(trail_lo, trail_hi)]
        lead = [imu[s].ax for s in range(lead_lo, lead_hi)]
        if len(trail) != IMU_BIAS_BLOCK or len(lead) != IMU_BIAS_BLOCK:
            continue
        if not all(math.isfinite(x) for x in trail + lead):
            continue
        delta = float(np.mean(trail)) - float(np.mean(lead))
        if abs(delta) >= IMU_BIAS_DELTA:
            flags.append(
                Flag(
                    t=imu[end_seq].t,
                    seq=end_seq,
                    stream="imu",
                    detector="imu_bias",
                    code="imu_bias",
                    value=delta,
                    t_host=end_seq * 0.01,
                )
            )
    return flags


def detect_gyro_dropout(imu: tuple[ImuSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    prev_t: float | None = None
    for s in imu:
        gx, gy, gz = s.gx, s.gy, s.gz
        nan_g = not np.isfinite(gx) or not np.isfinite(gy) or not np.isfinite(gz)
        gap = False
        if prev_t is not None and math.isfinite(s.t):
            gap = (s.t - prev_t) > 2.5 * 0.01
        if nan_g or gap:
            flags.append(
                Flag(
                    t=s.t,
                    seq=s.seq,
                    stream="imu",
                    detector="gyro_dropout",
                    code="gyro_dropout",
                    value=1.0 if nan_g else s.t - (prev_t or s.t),
                    t_host=s.seq * 0.01,
                )
            )
            break
        if math.isfinite(s.t):
            prev_t = s.t
    return flags


def _detect_stuck_sensor(log: RunLog) -> list[Flag]:
    imu = log.imu
    act_by_seq = {a.seq: a for a in log.actuator}
    flags: list[Flag] = []
    for end_seq in range(STUCK_IMU_BLOCK, len(imu)):
        lo = end_seq - STUCK_IMU_BLOCK
        gz_vals: list[float] = []
        for seq in range(lo, end_seq):
            v = imu[seq].gz
            if not math.isfinite(v):
                gz_vals = []
                break
            gz_vals.append(v)
        if len(gz_vals) != STUCK_IMU_BLOCK:
            continue
        arr = np.array(gz_vals, dtype=float)
        var = float(np.var(arr, ddof=0))
        if var >= STUCK_VAR or arr.max() != arr.min():
            continue
        lo_act = lo // 2
        hi_act = end_seq // 2
        speeds = [
            max(abs(act_by_seq[s].left_meas), abs(act_by_seq[s].right_meas))
            for s in range(lo_act, hi_act)
            if s in act_by_seq
        ]
        if not speeds or float(np.mean(speeds)) <= 0.05:
            continue
        edge = imu[end_seq]
        flags.append(
            Flag(
                t=edge.t,
                seq=end_seq,
                stream="imu",
                detector="stuck_sensor",
                code="stuck_sensor",
                value=var,
                t_host=end_seq * 0.01,
            )
        )
        break
    return flags


def _detect_timestamp_gap(pose: tuple[PoseSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    for i in range(1, len(pose)):
        prev, cur = pose[i - 1], pose[i]
        dt = cur.t - prev.t
        if dt > GAP_TH and cur.seq >= prev.seq + 2:
            flags.append(
                Flag(
                    t=cur.t,
                    seq=cur.seq,
                    stream="pose",
                    detector="timestamp_gap",
                    code="timestamp_gap",
                    value=dt,
                    t_host=cur.seq * 0.02,
                )
            )
            break
    return flags


def _detect_timestamp_jump(pose: tuple[PoseSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    for i in range(1, len(pose)):
        prev, cur = pose[i - 1], pose[i]
        dt = cur.t - prev.t
        if dt <= 0:
            flags.append(
                Flag(
                    t=cur.t,
                    seq=cur.seq,
                    stream="pose",
                    detector="timestamp_jump",
                    code="timestamp_jump",
                    value=dt,
                    t_host=cur.seq * 0.02,
                )
            )
    return flags


def _detect_actuator_sat(actuator: tuple[ActuatorSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    if not actuator:
        return flags
    act_by_seq = {a.seq: a for a in actuator}
    max_seq = max(a.seq for a in actuator)
    for end_seq in range(SAT_DWELL_SAMPLES, max_seq + 1):
        lo = end_seq - SAT_DWELL_SAMPLES
        window = [act_by_seq[s] for s in range(lo, end_seq) if s in act_by_seq]
        if len(window) != SAT_DWELL_SAMPLES:
            continue
        for side in ("left", "right"):
            if _sat_side(window, side):
                s = act_by_seq[end_seq]
                flags.append(
                    Flag(
                        t=s.t,
                        seq=end_seq,
                        stream="actuator",
                        detector="actuator_sat",
                        code="actuator_sat",
                        value=U_MAX,
                        t_host=end_seq * 0.02,
                    )
                )
                return flags
    return flags


def _sat_side(window: list[ActuatorSample], side: str) -> bool:
    if len(window) != SAT_DWELL_SAMPLES:
        return False
    cmd_ok = False
    for s in window:
        if side == "left":
            if abs(s.left_meas) < U_MAX - 1e-9:
                return False
            if abs(s.left_cmd) > U_MAX:
                cmd_ok = True
        else:
            if abs(s.right_meas) < U_MAX - 1e-9:
                return False
            if abs(s.right_cmd) > U_MAX:
                cmd_ok = True
    return cmd_ok


def _detect_pose_jump(pose: tuple[PoseSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    for i in range(1, len(pose)):
        prev, cur = pose[i - 1], pose[i]
        dt = cur.t - prev.t
        if dt <= 0:
            continue
        dx = cur.x - prev.x
        dy = cur.y - prev.y
        dist = math.hypot(dx, dy)
        limit = POSE_V_MAX * dt + 0.05
        if dist > limit:
            flags.append(
                Flag(
                    t=cur.t,
                    seq=cur.seq,
                    stream="pose",
                    detector="pose_jump",
                    code="pose_jump",
                    value=dist,
                    t_host=cur.seq * 0.02,
                )
            )
    return flags


def _wrap_angle(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _pose_yaw_rates(pose: tuple[PoseSample, ...]) -> tuple[list[float], list[float]]:
    mids: list[float] = []
    rates: list[float] = []
    for i in range(1, len(pose)):
        prev, cur = pose[i - 1], pose[i]
        if cur.seq - prev.seq >= 2:
            continue
        if cur.t <= prev.t:
            continue
        dyaw = _wrap_angle(cur.yaw - prev.yaw)
        dt = (cur.seq - prev.seq) * 0.02
        rate = dyaw / dt
        t_mid = 0.5 * (prev.seq + cur.seq) * 0.02
        mids.append(t_mid)
        rates.append(rate)
    return mids, rates


def _rolling_mean_imu_gz_seq(imu: tuple[ImuSample, ...], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(imu)
    for i in range(n, len(imu)):
        chunk: list[float] = []
        for j in range(i - n, i):
            v = imu[j].gz
            if not math.isfinite(v):
                chunk = []
                break
            chunk.append(v)
        if len(chunk) == n:
            out[i] = float(sum(chunk) / n)
    return out


def _smooth_pose_rates(
    rate_mids: list[float], rate_raw: list[float], window: float
) -> list[float | None]:
    out: list[float | None] = [None] * len(rate_mids)
    lo = 0
    for hi in range(len(rate_mids)):
        tq = rate_mids[hi]
        while lo < hi and rate_mids[lo] < tq - window:
            lo += 1
        if tq - window < rate_mids[0]:
            continue
        chunk = rate_raw[lo:hi]
        if not chunk:
            continue
        out[hi] = float(sum(chunk) / len(chunk))
    return out


def _interp_pose_gap_ok(
    t_q: np.ndarray, fit_t: np.ndarray, max_gap: float = 0.04
) -> np.ndarray:
    if len(fit_t) < 2:
        return np.zeros(t_q.shape, dtype=bool)
    idx = np.searchsorted(fit_t, t_q, side="right") - 1
    idx = np.clip(idx, 0, len(fit_t) - 2)
    seg = fit_t[idx + 1] - fit_t[idx]
    return seg <= max_gap + 1e-9


def _detect_clock_drift(log: RunLog) -> list[Flag]:
    imu = log.imu
    for win in analyze_clock_drift_windows(log):
        if (
            win.identifiable
            and win.delta is not None
            and abs(win.delta) >= DRIFT_ABS
        ):
            seq_flag = (
                win.imu_end_seq if win.imu_end_seq < len(imu) else len(imu) - 1
            )
            if seq_flag < 0:
                continue
            s = imu[seq_flag]
            return [
                Flag(
                    t=s.t,
                    seq=seq_flag,
                    stream="imu",
                    detector="clock_drift",
                    code="clock_drift",
                    value=win.delta,
                    t_host=win.t_host_end,
                )
            ]
    return []
