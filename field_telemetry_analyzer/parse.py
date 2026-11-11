# SPDX-License-Identifier: Apache-2.0
"""CSV and JSONL parsers for run logs."""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path

from field_telemetry_analyzer.models import (
    ActuatorSample,
    ImuSample,
    ParseError,
    PoseSample,
    RunLog,
)

IMU_COLS = ("t", "seq", "ax", "ay", "az", "gx", "gy", "gz")
POSE_COLS = ("t", "seq", "x", "y", "yaw")
ACT_COLS = ("t", "seq", "left_cmd", "right_cmd", "left_meas", "right_meas")


def parse_csv_dir(path: str | os.PathLike[str]) -> RunLog:
    base = Path(path)
    imu_p = base / "imu.csv"
    pose_p = base / "pose.csv"
    act_p = base / "actuator.csv"
    imu = _parse_imu_csv(imu_p)
    pose = _parse_pose_csv(pose_p)
    act = _parse_actuator_csv(act_p)
    return RunLog(imu=tuple(imu), pose=tuple(pose), actuator=tuple(act))


def parse_jsonl(path: str | os.PathLike[str]) -> RunLog:
    p = Path(path)
    if not p.is_file():
        raise ParseError("empty_log", "missing jsonl")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise ParseError("empty_log", "empty jsonl")
    imu: list[ImuSample] = []
    pose: list[PoseSample] = []
    act: list[ActuatorSample] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ParseError("empty_log", f"blank line {lineno}")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseError("invalid_json", str(exc)) from exc
        topic = obj.get("topic")
        if topic not in ("/imu/data", "/pose", "/actuator"):
            raise ParseError("unknown_topic", f"topic {topic!r}")
        data = obj.get("data")
        if not isinstance(data, dict):
            raise ParseError("invalid_field", "missing data dict")
        t = _parse_timestamp(obj.get("t"), "t")
        seq = _parse_seq(obj.get("seq"))
        if topic == "/imu/data":
            imu.append(
                ImuSample(
                    t=t,
                    seq=seq,
                    ax=_parse_float_field(data, "ax", gyro_ok=False),
                    ay=_parse_float_field(data, "ay", gyro_ok=False),
                    az=_parse_float_field(data, "az", gyro_ok=False),
                    gx=_parse_float_field(data, "gx", gyro_ok=True),
                    gy=_parse_float_field(data, "gy", gyro_ok=True),
                    gz=_parse_float_field(data, "gz", gyro_ok=True),
                )
            )
        elif topic == "/pose":
            pose.append(
                PoseSample(
                    t=t,
                    seq=seq,
                    x=_parse_float_field(data, "x", gyro_ok=False),
                    y=_parse_float_field(data, "y", gyro_ok=False),
                    yaw=_parse_float_field(data, "yaw", gyro_ok=False),
                )
            )
        else:
            act.append(
                ActuatorSample(
                    t=t,
                    seq=seq,
                    left_cmd=_parse_float_field(data, "left_cmd", gyro_ok=False),
                    right_cmd=_parse_float_field(data, "right_cmd", gyro_ok=False),
                    left_meas=_parse_float_field(data, "left_meas", gyro_ok=False),
                    right_meas=_parse_float_field(data, "right_meas", gyro_ok=False),
                )
            )
    _check_seq(imu, "imu")
    _check_seq(pose, "pose")
    _check_seq(act, "actuator")
    return RunLog(imu=tuple(imu), pose=tuple(pose), actuator=tuple(act))


def _parse_imu_csv(path: Path) -> list[ImuSample]:
    rows, _hdr = _read_csv(path, IMU_COLS)
    out: list[ImuSample] = []
    for row in rows:
        t = _parse_timestamp(row["t"], "t")
        seq = _parse_seq(row["seq"])
        out.append(
            ImuSample(
                t=t,
                seq=seq,
                ax=_parse_csv_float(row["ax"], "ax", gyro=False),
                ay=_parse_csv_float(row["ay"], "ay", gyro=False),
                az=_parse_csv_float(row["az"], "az", gyro=False),
                gx=_parse_csv_float(row["gx"], "gx", gyro=True),
                gy=_parse_csv_float(row["gy"], "gy", gyro=True),
                gz=_parse_csv_float(row["gz"], "gz", gyro=True),
            )
        )
    _check_seq(out, "imu")
    return out


def _parse_pose_csv(path: Path) -> list[PoseSample]:
    rows, _ = _read_csv(path, POSE_COLS)
    out: list[PoseSample] = []
    for row in rows:
        out.append(
            PoseSample(
                t=_parse_timestamp(row["t"], "t"),
                seq=_parse_seq(row["seq"]),
                x=_parse_csv_float(row["x"], "x", gyro=False),
                y=_parse_csv_float(row["y"], "y", gyro=False),
                yaw=_parse_csv_float(row["yaw"], "yaw", gyro=False),
            )
        )
    _check_seq(out, "pose")
    return out


def _parse_actuator_csv(path: Path) -> list[ActuatorSample]:
    rows, _ = _read_csv(path, ACT_COLS)
    out: list[ActuatorSample] = []
    for row in rows:
        out.append(
            ActuatorSample(
                t=_parse_timestamp(row["t"], "t"),
                seq=_parse_seq(row["seq"]),
                left_cmd=_parse_csv_float(row["left_cmd"], "left_cmd", gyro=False),
                right_cmd=_parse_csv_float(row["right_cmd"], "right_cmd", gyro=False),
                left_meas=_parse_csv_float(row["left_meas"], "left_meas", gyro=False),
                right_meas=_parse_csv_float(row["right_meas"], "right_meas", gyro=False),
            )
        )
    _check_seq(out, "actuator")
    return out


def _read_csv(path: Path, required: tuple[str, ...]) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        raise ParseError("empty_log", f"missing {path.name}")
    with path.open(newline="") as f:
        reader = csv.reader(f)
        try:
            hdr = next(reader)
        except StopIteration:
            raise ParseError("empty_log", "header only") from None
        hdr_set = set(hdr)
        for col in required:
            if col not in hdr_set:
                raise ParseError("missing_column", col)
        if len(hdr) != len(set(hdr)):
            raise ParseError("invalid_field", "duplicate column")
        extra = [c for c in hdr if c not in required]
        if extra:
            raise ParseError("invalid_field", f"extra column {extra[0]}")
        rows: list[dict[str, str]] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(hdr):
                raise ParseError("invalid_field", "column count")
            rows.append(dict(zip(hdr, row, strict=True)))
        if not rows:
            raise ParseError("empty_log", "no data rows")
    return rows, hdr


def _parse_timestamp(raw: object, field: str) -> float:
    if raw is None:
        raise ParseError("invalid_timestamp", field)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == "nan":
            raise ParseError("invalid_timestamp", field)
        try:
            val = float(raw)
        except ValueError as exc:
            raise ParseError("invalid_timestamp", field) from exc
    elif isinstance(raw, (int, float)):
        val = float(raw)
    else:
        raise ParseError("invalid_timestamp", field)
    if not math.isfinite(val):
        raise ParseError("invalid_timestamp", field)
    return val


def _parse_seq(raw: object) -> int:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    raise ParseError("invalid_field", "seq")


def _parse_csv_float(raw: str, field: str, gyro: bool) -> float:
    s = raw.strip().lower()
    if s == "nan":
        if gyro:
            return float("nan")
        raise ParseError("invalid_field", field)
    if s in ("inf", "+inf", "-inf", "infinity"):
        raise ParseError("invalid_field", field)
    try:
        val = float(raw)
    except ValueError as exc:
        raise ParseError("invalid_field", field) from exc
    if not math.isfinite(val) and not (gyro and math.isnan(val)):
        raise ParseError("invalid_field", field)
    return val


def _parse_float_field(data: dict, key: str, gyro_ok: bool) -> float:
    if key not in data:
        raise ParseError("invalid_field", key)
    val = data[key]
    if isinstance(val, str):
        return _parse_csv_float(val, key, gyro=gyro_ok)
    if isinstance(val, bool):
        raise ParseError("invalid_field", key)
    if isinstance(val, (int, float)):
        if (
            not math.isfinite(float(val))
            and not (gyro_ok and math.isnan(float(val)))
            and math.isinf(float(val))
        ):
            raise ParseError("invalid_field", key)
        return float(val)
    raise ParseError("invalid_field", key)


def _check_seq(samples: list, stream: str) -> None:
    prev: int | None = None
    for s in samples:
        if prev is not None and s.seq <= prev:
            raise ParseError("invalid_field", f"{stream} seq")
        prev = s.seq
