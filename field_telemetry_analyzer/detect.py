# SPDX-License-Identifier: Apache-2.0
"""Deterministic explainable detectors (numpy only, no ML)."""
from __future__ import annotations

import math
from collections.abc import Collection

import numpy as np

from field_telemetry_analyzer.kinematics import U_MAX
from field_telemetry_analyzer.models import ActuatorSample, Flag, ImuSample, PoseSample, RunLog

IMU_BIAS_DELTA = 0.25
IMU_BIAS_W = 0.20
STUCK_VAR = 2.5e-7
STUCK_W = 0.30
GAP_TH = 0.10
SAT_DWELL = 0.20
POSE_V_MAX = 0.80
DRIFT_ABS = 0.08

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


def _t_host_imu(seq: int) -> float:
    return seq * 0.01


def _t_host_pose(seq: int) -> float:
    return seq * 0.02


def _detect_imu_bias(imu: tuple[ImuSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    if not imu:
        return flags
    t_end = imu[-1].t
    k = 2
    while True:
        t_edge = k * IMU_BIAS_W
        if t_edge > t_end + 1e-9:
            break
        ax_trail = _block_mean_ax(imu, t_edge - IMU_BIAS_W, t_edge)
        ax_lead = _block_mean_ax(imu, t_edge - 2 * IMU_BIAS_W, t_edge - IMU_BIAS_W)
        if ax_trail is not None and ax_lead is not None:
            delta = ax_trail - ax_lead
            if abs(delta) >= IMU_BIAS_DELTA:
                seq = round(t_edge / 0.01)
                flags.append(
                    Flag(
                        t=imu[seq].t,
                        seq=seq,
                        stream="imu",
                        detector="imu_bias",
                        code="imu_bias",
                        value=delta,
                        t_host=_t_host_imu(seq),
                    )
                )
        k += 1
    return flags


def _block_mean_ax(imu: tuple[ImuSample, ...], t0: float, t1: float) -> float | None:
    vals = []
    for s in imu:
        th = _t_host_imu(s.seq)
        if t0 <= th < t1:
            if not math.isfinite(s.ax):
                return None
            vals.append(s.ax)
    if not vals:
        return None
    return float(np.mean(vals))


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
                    t_host=_t_host_imu(s.seq),
                )
            )
            break
        if math.isfinite(s.t):
            prev_t = s.t
    return flags


def _detect_stuck_sensor(log: RunLog) -> list[Flag]:
    imu = log.imu
    n_in_win = round(STUCK_W / 0.01)
    flags: list[Flag] = []
    for end_seq in range(n_in_win, 6000):
        t1 = end_seq * 0.01
        t0 = t1 - STUCK_W
        lo = end_seq - n_in_win
        gz_vals: list[float] = []
        for seq in range(lo, end_seq):
            s = imu[seq]
            if not math.isfinite(s.gz):
                gz_vals = []
                break
            gz_vals.append(s.gz)
        if len(gz_vals) != n_in_win:
            continue
        arr = np.array(gz_vals, dtype=float)
        var = float(np.var(arr, ddof=0))
        if var >= STUCK_VAR:
            continue
        if arr.max() != arr.min():
            continue
        if not _actuator_motion_in_window(log.actuator, t0, t1):
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
                t_host=t1,
            )
        )
        break
    return flags


def _actuator_motion_in_window(
    actuator: tuple[ActuatorSample, ...], t0: float, t1: float
) -> bool:
    speeds = []
    for s in actuator:
        th = _t_host_pose(s.seq)
        if t0 <= th < t1:
            speeds.append(max(abs(s.left_meas), abs(s.right_meas)))
    if not speeds:
        return False
    return float(np.mean(speeds)) > 0.05


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
                    t_host=_t_host_pose(cur.seq),
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
                    t_host=_t_host_pose(cur.seq),
                )
            )
    return flags


def _detect_actuator_sat(actuator: tuple[ActuatorSample, ...]) -> list[Flag]:
    flags: list[Flag] = []
    n_in_win = round(SAT_DWELL / 0.02)
    if not actuator:
        return flags
    for end_seq in range(n_in_win, 3000):
        t1 = end_seq * 0.02
        t0 = t1 - SAT_DWELL
        window = [s for s in actuator if t0 <= _t_host_pose(s.seq) < t1]
        if len(window) < n_in_win:
            continue
        for side in ("left", "right"):
            if _sat_side(window, side):
                s = next(x for x in actuator if x.seq == end_seq)
                flags.append(
                    Flag(
                        t=s.t,
                        seq=end_seq,
                        stream="actuator",
                        detector="actuator_sat",
                        code="actuator_sat",
                        value=U_MAX,
                        t_host=t1,
                    )
                )
                return flags
    return flags


def _sat_side(window: list[ActuatorSample], side: str) -> bool:
    if not window:
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
                    t_host=_t_host_pose(cur.seq),
                )
            )
    return flags


def _wrap_angle(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _trailing_mean_times(
    times: list[float], values: list[float], t_query: float, window: float
) -> float | None:
    if not times:
        return None
    t0 = t_query - window
    acc: list[float] = []
    for t, v in zip(times, values, strict=True):
        if t0 <= t < t_query:
            if not math.isfinite(v):
                return None
            acc.append(v)
    if not acc:
        return None
    return float(np.mean(acc))


def _pose_yaw_rates(pose: tuple[PoseSample, ...]) -> tuple[list[float], list[float], list[float]]:
    """Return host midpoints, raw interval rates, host stamp pairs for smoothing."""
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
        t_mid = 0.5 * (_t_host_pose(prev.seq) + _t_host_pose(cur.seq))
        mids.append(t_mid)
        rates.append(rate)
    return mids, rates, mids


def _rolling_mean_imu_gz(imu: tuple[ImuSample, ...], window: float) -> list[float | None]:
    n = round(window / 0.01)
    out: list[float | None] = [None] * len(imu)
    for i in range(len(imu)):
        lo = i - n
        if lo < 0:
            continue
        chunk: list[float] = []
        for j in range(lo, i):
            v = imu[j].gz
            if not math.isfinite(v):
                out[i] = None
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


def _detect_clock_drift(log: RunLog) -> list[Flag]:
    pose = log.pose
    imu = log.imu
    rate_mids, rate_raw, _ = _pose_yaw_rates(pose)
    if not rate_mids:
        return []

    imu_hosts = [_t_host_imu(s.seq) for s in imu]
    imu_stamps = [s.t for s in imu]

    smooth_rate = _smooth_pose_rates(rate_mids, rate_raw, 0.20)
    smooth_gz = _rolling_mean_imu_gz(imu, 0.20)

    t0 = 2.5
    while t0 + 5.0 <= 60.0 + 1e-9:
        t1 = t0 + 5.0
        in_win = [(m, r) for m, r in zip(rate_mids, smooth_rate, strict=True) if t0 <= m < t1 and r is not None]
        if len(in_win) < 2:
            t0 += 2.5
            continue
        ptp = max(v for _, v in in_win) - min(v for _, v in in_win)
        if ptp < 0.20:
            t0 += 2.5
            continue
        fit_times = np.array(rate_mids, dtype=float)
        fit_rates = np.array(
            [r if r is not None else np.nan for r in smooth_rate], dtype=float
        )
        valid = np.isfinite(fit_rates)
        fit_times = fit_times[valid]
        fit_rates = fit_rates[valid]
        if fit_times.size < 2:
            t0 += 2.5
            continue
        t_lo, t_hi = fit_times[0], fit_times[-1]
        idxs = [
            i
            for i, th in enumerate(imu_hosts)
            if t0 <= th < t1 and smooth_gz[i] is not None
        ]
        if len(idxs) < 10:
            t0 += 2.5
            continue
        gz_arr = np.array([smooth_gz[i] for i in idxs], dtype=float)
        stamp_arr = np.array([imu_stamps[i] for i in idxs], dtype=float)
        best_sse = float("inf")
        best_delta = 0.0
        best_pairs = len(idxs)
        for delta_i in range(-100, 101):
            delta = delta_i * 0.01
            t_q = stamp_arr - delta
            in_sup = (t_q >= t_lo) & (t_q <= t_hi)
            if int(in_sup.sum()) < 10:
                continue
            rate_v = np.interp(t_q[in_sup], fit_times, fit_rates)
            sse = float(np.sum((gz_arr[in_sup] - rate_v) ** 2))
            if sse < best_sse - 1e-15:
                best_sse = sse
                best_delta = delta
            elif (
                abs(sse - best_sse) <= 1e-12
                and (
                    abs(delta) < abs(best_delta)
                    or abs(delta) == abs(best_delta)
                    and delta < best_delta
                )
            ):
                best_delta = delta
        if best_pairs < 10 or abs(best_delta) >= 1.0 - 1e-9:
            t0 += 2.5
            continue
        if abs(best_delta) >= DRIFT_ABS:
            end_seq = round(t1 / 0.01)
            s = imu[end_seq]
            return [
                Flag(
                    t=s.t,
                    seq=end_seq,
                    stream="imu",
                    detector="clock_drift",
                    code="clock_drift",
                    value=best_delta,
                    t_host=t1,
                )
            ]
        t0 += 2.5
    return []


def _interp_linear(
    times: list[float], values: list[float | None], t: float
) -> float | None:
    if not times or t < times[0] or t > times[-1]:
        return None
    i = int(np.searchsorted(times, t, side="right")) - 1
    if i < 0 or i >= len(times) - 1:
        return None
    if values[i] is None or values[i + 1] is None:
        return None
    t0, t1 = times[i], times[i + 1]
    if t1 == t0:
        return values[i]
    frac = (t - t0) / (t1 - t0)
    return values[i] + frac * (values[i + 1] - values[i])
