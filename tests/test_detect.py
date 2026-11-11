# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import subprocess
import sys
import tempfile

import pytest

import field_telemetry_analyzer.detect as detect_mod
from field_telemetry_analyzer.detect import _detect_clock_drift, detect
from field_telemetry_analyzer.generate import generate, write_run
from field_telemetry_analyzer.score import score

SEED = 20261110


def test_imu_bias_f1_block_delta(standard_log) -> None:
    log, _ = standard_log
    imu = log.imu
    trail = [imu[s].ax for s in range(1200, 1220)]
    lead = [imu[s].ax for s in range(1180, 1200)]
    delta = sum(trail) / 20 - sum(lead) / 20
    assert abs(delta - 0.392092) < 1e-5
    flag = next(f for f in detect(log) if f.detector == "imu_bias" and f.seq == 1220)
    assert flag.value == delta


def test_clock_drift_high_gate_flags_last_window(standard_log, monkeypatch) -> None:
    log, _ = standard_log
    monkeypatch.setattr(detect_mod, "DRIFT_ABS", 0.15)
    flags = _detect_clock_drift(log)
    assert len(flags) == 1
    assert flags[0].seq == len(log.imu) - 1
    assert flags[0].t_host == 60.0


def test_standard_precision_recall(standard_log) -> None:
    log, events = standard_log
    flags = detect(log)
    sc = score(flags, events)
    assert sc.tp == 8
    assert sc.fp == 0
    assert sc.fn == 0
    assert sc.precision == 1.0
    assert sc.recall == 1.0


def test_clean_zero_flags(clean_log) -> None:
    log, _ = clean_log
    assert detect(log) == []


def _assert_latency(standard_log, detector: str, expected_us: int) -> None:
    log, events = standard_log
    sc = score(detect(log), events)
    row = next(f for f in sc.faults if f.detector == detector)
    assert row.outcome == "TP"
    assert row.latency_us == expected_us


def test_latency_imu_bias(standard_log) -> None:
    _assert_latency(standard_log, "imu_bias", 200000)


def test_latency_gyro_dropout(standard_log) -> None:
    _assert_latency(standard_log, "gyro_dropout", 0)


def test_latency_stuck_sensor(standard_log) -> None:
    _assert_latency(standard_log, "stuck_sensor", 300000)


def test_latency_timestamp_gap(standard_log) -> None:
    _assert_latency(standard_log, "timestamp_gap", 400000)


def test_latency_timestamp_jump(standard_log) -> None:
    _assert_latency(standard_log, "timestamp_jump", 0)


def test_latency_actuator_sat(standard_log) -> None:
    _assert_latency(standard_log, "actuator_sat", 200000)


def test_latency_pose_jump(standard_log) -> None:
    _assert_latency(standard_log, "pose_jump", 0)


def test_latency_clock_drift(standard_log) -> None:
    _assert_latency(standard_log, "clock_drift", 7000000)


def test_timestamp_disambiguation(standard_log) -> None:
    log, _ = standard_log
    flags = detect(log)
    assert sum(1 for f in flags if f.detector == "timestamp_gap") == 1
    assert sum(1 for f in flags if f.detector == "timestamp_jump") == 1
    recovery = next(p for p in log.pose if p.seq == 2251)
    assert recovery.t == 45.02


@pytest.mark.parametrize(
    "detector",
    [
        "imu_bias",
        "gyro_dropout",
        "stuck_sensor",
        "timestamp_gap",
        "timestamp_jump",
        "actuator_sat",
        "pose_jump",
        "clock_drift",
    ],
)
def test_disable(standard_log, detector: str) -> None:
    log, events = standard_log
    sc = score(detect(log, disable={detector}), events)
    row = next(f for f in sc.faults if f.detector == detector)
    assert row.outcome == "FN"


def test_disable_cli_imu_bias() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "field_telemetry_analyzer.cli",
                "detect",
                "--log",
                d,
                "--out",
                out,
                "--disable",
                "imu_bias",
            ],
            capture_output=True,
            check=False,
        )
        assert r.returncode == 0
