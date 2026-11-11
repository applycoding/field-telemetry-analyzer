# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from field_telemetry_analyzer.generate import generate, write_run
from field_telemetry_analyzer.models import (
    ActuatorSample,
    ImuSample,
    ParseError,
    PoseSample,
)
from field_telemetry_analyzer.parse import parse_csv_dir, parse_jsonl

SEED = 20261110


def _field_eq(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return a == b


def _imu_eq(a: ImuSample, b: ImuSample) -> bool:
    return (
        a.seq == b.seq
        and _field_eq(a.t, b.t)
        and _field_eq(a.ax, b.ax)
        and _field_eq(a.ay, b.ay)
        and _field_eq(a.az, b.az)
        and _field_eq(a.gx, b.gx)
        and _field_eq(a.gy, b.gy)
        and _field_eq(a.gz, b.gz)
    )


def _pose_eq(a: PoseSample, b: PoseSample) -> bool:
    return (
        a.seq == b.seq
        and _field_eq(a.t, b.t)
        and _field_eq(a.x, b.x)
        and _field_eq(a.y, b.y)
        and _field_eq(a.yaw, b.yaw)
    )


def _act_eq(a: ActuatorSample, b: ActuatorSample) -> bool:
    return (
        a.seq == b.seq
        and _field_eq(a.t, b.t)
        and _field_eq(a.left_cmd, b.left_cmd)
        and _field_eq(a.right_cmd, b.right_cmd)
        and _field_eq(a.left_meas, b.left_meas)
        and _field_eq(a.right_meas, b.right_meas)
    )


def test_csv_jsonl_roundtrip(standard_log) -> None:
    log, _ = standard_log
    with tempfile.TemporaryDirectory() as d:
        write_run(log, (), d)
        csv_log = parse_csv_dir(d)
        json_log = parse_jsonl(Path(d) / "log.jsonl")
        assert len(csv_log.imu) == len(json_log.imu)
        assert len(csv_log.pose) == len(json_log.pose)
        assert len(csv_log.actuator) == len(json_log.actuator)
        for a, b in zip(csv_log.imu, json_log.imu, strict=True):
            assert _imu_eq(a, b)
        for a, b in zip(csv_log.pose, json_log.pose, strict=True):
            assert _pose_eq(a, b)
        for a, b in zip(csv_log.actuator, json_log.actuator, strict=True):
            assert _act_eq(a, b)


def _cli_detect_fail(log_dir: str, out_dir: str, *, fmt: str = "csv") -> None:
    cmd = [
        sys.executable,
        "-m",
        "field_telemetry_analyzer.cli",
        "detect",
        "--log",
        log_dir,
        "--out",
        out_dir,
        "--format",
        fmt,
    ]
    r = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 2
    assert not (Path(out_dir) / "score.json").exists()


def test_parse_missing_column() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        text = Path(d, "imu.csv").read_text(encoding="utf-8")
        Path(d, "imu.csv").write_text(text.replace("ax,", "axx,"), encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "missing_column"
        _cli_detect_fail(d, out)


def test_parse_invalid_timestamp() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        lines = Path(d, "imu.csv").read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1].replace("0.", "nan", 1)
        Path(d, "imu.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "invalid_timestamp"
        _cli_detect_fail(d, out)


def test_parse_empty_log() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        Path(d, "imu.csv").write_text("t,seq,ax,ay,az,gx,gy,gz\n", encoding="utf-8")
        Path(d, "pose.csv").write_text("t,seq,x,y,yaw\n0,0,0,0,0\n", encoding="utf-8")
        Path(d, "actuator.csv").write_text(
            "t,seq,left_cmd,right_cmd,left_meas,right_meas\n0,0,0,0,0,0\n", encoding="utf-8"
        )
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "empty_log"
        _cli_detect_fail(d, out)


def test_parse_invalid_json() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        Path(d, "log.jsonl").write_text("{not json\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_jsonl(Path(d) / "log.jsonl")
        assert exc.value.code == "invalid_json"
        _cli_detect_fail(d, out, fmt="jsonl")


def test_parse_unknown_topic() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        obj = {"t": 0.0, "seq": 0, "topic": "/bad", "type": "X", "data": {}}
        Path(d, "log.jsonl").write_text(json.dumps(obj) + "\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_jsonl(Path(d) / "log.jsonl")
        assert exc.value.code == "unknown_topic"
        _cli_detect_fail(d, out, fmt="jsonl")


def test_parse_invalid_field() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        lines = Path(d, "imu.csv").read_text(encoding="utf-8").splitlines()
        parts = lines[2].split(",")
        parts[1] = parts[0]
        lines[2] = ",".join(parts)
        Path(d, "imu.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "invalid_field"
        _cli_detect_fail(d, out)
