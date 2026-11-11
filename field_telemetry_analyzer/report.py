# SPDX-License-Identifier: Apache-2.0
"""HTML/Markdown report and matplotlib figures."""
from __future__ import annotations

import csv
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader, select_autoescape

from field_telemetry_analyzer.detect import analyze_clock_drift_windows
from field_telemetry_analyzer.models import Event, Flag, RunLog, Score

TITLE = "Field telemetry analyzer (synthetic data only)"
BANNER = "These are not real field logs."


def write_report(
    log: RunLog,
    flags: list[Flag],
    score: Score,
    out_dir: str | Path,
    truth: tuple[Event, ...] | None = None,
) -> None:
    out = Path(out_dir)
    os.makedirs(out, exist_ok=True)
    drift_windows = analyze_clock_drift_windows(log)
    _write_flags_csv(out / "flags.csv", flags)
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    context = {
        "title": TITLE,
        "banner": BANNER,
        "score": score,
        "n_flags": len(flags),
        "synthetic_notice": BANNER,
        "flags": sorted(flags, key=lambda f: (f.t_host, f.stream, f.detector, f.seq)),
        "faults": score.faults,
    }
    md = env.get_template("report.md.j2").render(**context)
    html = env.get_template("report.html.j2").render(**context)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.html").write_text(html, encoding="utf-8")
    (out / "index.html").write_text(html, encoding="utf-8")
    _plot_imu(out / "imu.png", log, flags, truth)
    _plot_pose_path(out / "pose_path.png", log)
    _plot_pose_time(out / "pose_time.png", log, flags)
    _plot_actuator(out / "actuator.png", log, flags)
    _plot_clock_offset(out / "clock_offset.png", drift_windows)
    _plot_flags(out / "flags.png", flags)


def _write_flags_csv(path: Path, flags: list[Flag]) -> None:
    rows = sorted(flags, key=lambda f: (f.t_host, f.stream, f.detector, f.seq))
    with path.open("w", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["t", "seq", "stream", "detector", "code", "value", "t_host"])
        for fl in rows:
            w.writerow(
                [
                    f"{fl.t:.6f}",
                    fl.seq,
                    fl.stream,
                    fl.detector,
                    fl.code,
                    format(fl.value, ".17g"),
                    format(fl.t_host, ".17g"),
                ]
            )


def _plot_imu(
    path: Path, log: RunLog, flags: list[Flag], truth: tuple[Event, ...] | None
) -> None:
    t = [s.seq * 0.01 for s in log.imu]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(t, [s.ax for s in log.imu], label="ax")
    axes[0].plot(t, [s.ay for s in log.imu], label="ay")
    axes[0].plot(t, [s.az for s in log.imu], label="az")
    axes[0].set_ylabel("accel m/s^2")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].plot(t, [s.gx for s in log.imu], label="gx")
    axes[1].plot(t, [s.gy for s in log.imu], label="gy")
    axes[1].plot(t, [s.gz for s in log.imu], label="gz")
    axes[1].set_ylabel("gyro rad/s")
    axes[1].set_xlabel("host time s")
    for fl in flags:
        if fl.stream == "imu":
            for ax in axes:
                ax.axvline(fl.t_host, color="red", alpha=0.3, linewidth=0.8)
    if truth:
        for ev in truth:
            if ev.detector == "imu_bias":
                axes[0].axvspan(ev.t_start, 60.0, alpha=0.1, color="orange")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _plot_pose_path(path: Path, log: RunLog) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([s.x for s in log.pose], [s.y for s in log.pose])
    ax.set_xlabel("x m")
    ax.set_ylabel("y m")
    ax.set_title("Pose path (synthetic)")
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _plot_pose_time(path: Path, log: RunLog, flags: list[Flag]) -> None:
    t = [s.seq * 0.02 for s in log.pose]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, [s.yaw for s in log.pose])
    ax.set_xlabel("host time s")
    ax.set_ylabel("yaw rad")
    for fl in flags:
        if fl.stream == "pose":
            ax.axvline(fl.t_host, color="red", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _plot_actuator(path: Path, log: RunLog, flags: list[Flag]) -> None:
    t = [s.seq * 0.02 for s in log.actuator]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, [s.left_meas for s in log.actuator], label="left_meas")
    ax.plot(t, [s.right_meas for s in log.actuator], label="right_meas")
    ax.legend()
    ax.set_xlabel("host time s")
    for fl in flags:
        if fl.stream == "actuator":
            ax.axvline(fl.t_host, color="red", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _plot_clock_offset(path: Path, windows: list) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    for w in windows:
        if w.identifiable and w.delta is not None:
            ax.scatter(w.t_host_end, w.delta, color="tab:blue", s=24)
        else:
            ax.scatter(w.t_host_end, 0.0, color="tab:gray", marker="x", s=30)
    ax.axhline(0.08, color="red", linestyle="--", linewidth=1, label="0.08 s gate")
    ax.axhline(-0.08, color="red", linestyle="--", linewidth=1)
    ax.set_xlabel("window right edge (host time s)")
    ax.set_ylabel("lag estimate delta (s)")
    ax.set_title("Clock drift lag grid (synthetic)")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _plot_flags(path: Path, flags: list[Flag]) -> None:
    fig, ax = plt.subplots(figsize=(10, 3))
    dets = sorted({f.detector for f in flags})
    ymap = {d: i for i, d in enumerate(dets)}
    for fl in flags:
        ax.scatter(fl.t_host, ymap[fl.detector], s=20)
    ax.set_yticks(range(len(dets)), dets)
    ax.set_xlabel("t_host s")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
