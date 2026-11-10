# SPDX-License-Identifier: Apache-2.0
"""Planar differential-drive kinematic truth for the seeded simulator."""
from __future__ import annotations

import math

G = 9.80665
V_MAX = 0.80
OMEGA_MAX = 1.20
WHEELBASE = 0.30
U_MAX = 1.00


def velocity_omega(t: float) -> tuple[float, float]:
    if t < 0.0 or t >= 60.0:
        raise ValueError("t out of range")
    if t < 5.0:
        return 0.0, 0.0
    if t < 8.0:
        return 0.20 * (t - 5.0), 0.0
    if t < 16.0:
        return 0.60, 0.0
    if t < 20.0:
        return 0.60, 0.40
    if t < 28.0:
        return 0.50, 0.0
    if t < 36.0:
        return 0.40, 0.50
    if t < 48.0:
        return 0.40, 0.0
    v = 0.30
    w = 0.30 * math.sin(math.pi * (t - 48.0) / 2.0)
    return v, w


def velocity_derivative(t: float) -> float:
    if t < 5.0 or (8.0 <= t < 16.0) or (20.0 <= t < 28.0) or (36.0 <= t < 48.0):
        return 0.0
    if 5.0 <= t < 8.0:
        return 0.20
    return 0.0


def yaw_closed_form(t: float) -> float:
    if t <= 16.0:
        return 0.0
    if t <= 20.0:
        return 0.40 * (t - 16.0)
    if t <= 28.0:
        return 1.60
    if t <= 36.0:
        return 1.60 + 0.50 * (t - 28.0)
    if t <= 48.0:
        return 5.60
    return 5.60 + (0.60 / math.pi) * (1.0 - math.cos(math.pi * (t - 48.0) / 2.0))


def _arc_step(x: float, y: float, yaw: float, v: float, w: float, dt: float) -> tuple[float, float, float]:
    if abs(w) < 1e-15:
        return x + v * math.cos(yaw) * dt, y + v * math.sin(yaw) * dt, yaw
    yaw2 = yaw + w * dt
    s = v / w
    nx = x + s * (math.sin(yaw2) - math.sin(yaw))
    ny = y + s * (math.cos(yaw) - math.cos(yaw2))
    return nx, ny, yaw2


def _integrate_xy_to(t: float) -> tuple[float, float]:
    if t <= 0.0:
        return 0.0, 0.0
    x = y = yaw = 0.0
    dt = 0.01
    steps = round(t / dt)
    for k in range(1, steps + 1):
        t0 = (k - 1) * dt
        v0, w0 = velocity_omega(t0 + 1e-12)
        v1, w1 = velocity_omega(k * dt - 1e-12)
        v = 0.5 * (v0 + v1)
        w = w0 if abs(w0 - w1) < 1e-15 else 0.5 * (w0 + w1)
        x, y, yaw = _arc_step(x, y, yaw, v, w, dt)
    return x, y


def integrate_pose_100hz() -> tuple[list[float], list[float], list[float]]:
    n = 6000
    xs = [0.0] * n
    ys = [0.0] * n
    yaws = [0.0] * n
    for k in range(1, n):
        t = k * 0.01
        x, y = _integrate_xy_to(t)
        xs[k], ys[k], yaws[k] = x, y, yaw_closed_form(t)
    return xs, ys, yaws


def specific_force_at(t: float, v: float, omega: float) -> tuple[float, float, float, float, float, float]:
    ax = velocity_derivative(t)
    ay = v * omega
    az = G
    gx = gy = 0.0
    gz = omega
    return ax, ay, az, gx, gy, gz


def wheel_speeds(v: float, omega: float) -> tuple[float, float]:
    half = WHEELBASE / 2.0
    u_l = v - omega * half
    u_r = v + omega * half
    return u_l, u_r


def truth_pose_at(t: float) -> tuple[float, float, float]:
    if abs(t - 8.0) < 1e-9:
        return 0.90, 0.0, 0.0
    if abs(t - 16.0) < 1e-9:
        return 5.70, 0.0, 0.0
    if abs(t - 20.0) < 1e-9:
        yaw = 1.60
        x = 5.70 + 1.50 * math.sin(yaw)
        y = 1.50 * (1.0 - math.cos(yaw))
        return x, y, yaw
    if abs(t - 36.0) < 1e-9:
        return 5.777890122626, 4.898281374969, 5.60
    if abs(t - 48.0) < 1e-9:
        return 9.500606339475, 1.868201513182, 5.60
    x, y = _integrate_xy_to(t)
    return x, y, yaw_closed_form(t)
