# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from field_telemetry_analyzer.generate import generate, write_run
from field_telemetry_analyzer.models import ParseError
from field_telemetry_analyzer.parse import parse_csv_dir, parse_jsonl

SEED = 20261110


def test_csv_jsonl_roundtrip(standard_log) -> None:
    log, _ = standard_log
    with tempfile.TemporaryDirectory() as d:
        write_run(log, (), d)
        from field_telemetry_analyzer.generate import write_run as wr

        wr(log, (), d)
        csv_log = parse_csv_dir(d)
        json_log = parse_jsonl(Path(d) / "log.jsonl")
        assert len(csv_log.imu) == len(json_log.imu)
        for a, b in zip(csv_log.imu, json_log.imu, strict=True):
            assert a.seq == b.seq
            assert abs(a.ax - b.ax) < 1e-15 or (a.ax != a.ax and b.ax != b.ax)


def _run_detect_expect_2(log_dir: str) -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "field_telemetry_analyzer.cli",
            "detect",
            "--log",
            log_dir,
            "--out",
            tempfile.mkdtemp(),
        ],
        capture_output=True,
        check=False,
    )
    assert r.returncode == 2


def test_parse_missing_column() -> None:
    with tempfile.TemporaryDirectory() as d:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        text = Path(d, "imu.csv").read_text(encoding="utf-8")
        Path(d, "imu.csv").write_text(text.replace("ax,", "axx,"), encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "missing_column"
        _run_detect_expect_2(d)


def test_parse_invalid_timestamp() -> None:
    with tempfile.TemporaryDirectory() as d:
        log, ev = generate("standard", SEED)
        write_run(log, ev, d)
        lines = Path(d, "imu.csv").read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1].replace("0.", "nan", 1)
        Path(d, "imu.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "invalid_timestamp"


def test_parse_empty_log() -> None:
    with tempfile.TemporaryDirectory() as d:
        Path(d, "imu.csv").write_text("t,seq,ax,ay,az,gx,gy,gz\n", encoding="utf-8")
        Path(d, "pose.csv").write_text("t,seq,x,y,yaw\n0,0,0,0,0\n", encoding="utf-8")
        Path(d, "actuator.csv").write_text(
            "t,seq,left_cmd,right_cmd,left_meas,right_meas\n0,0,0,0,0,0\n", encoding="utf-8"
        )
        with pytest.raises(ParseError) as exc:
            parse_csv_dir(d)
        assert exc.value.code == "empty_log"


def test_parse_invalid_json() -> None:
    with tempfile.TemporaryDirectory() as d:
        Path(d, "log.jsonl").write_text("{not json\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_jsonl(Path(d) / "log.jsonl")
        assert exc.value.code == "invalid_json"


def test_parse_unknown_topic() -> None:
    with tempfile.TemporaryDirectory() as d:
        obj = {"t": 0.0, "seq": 0, "topic": "/bad", "type": "X", "data": {}}
        Path(d, "log.jsonl").write_text(json.dumps(obj) + "\n", encoding="utf-8")
        with pytest.raises(ParseError) as exc:
            parse_jsonl(Path(d) / "log.jsonl")
        assert exc.value.code == "unknown_topic"


def test_parse_invalid_field() -> None:
    with tempfile.TemporaryDirectory() as d:
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
