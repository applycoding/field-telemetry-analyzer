# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ImuSample:
    t: float
    seq: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


@dataclass(frozen=True)
class PoseSample:
    t: float
    seq: int
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class ActuatorSample:
    t: float
    seq: int
    left_cmd: float
    right_cmd: float
    left_meas: float
    right_meas: float


@dataclass(frozen=True)
class RunLog:
    imu: tuple[ImuSample, ...]
    pose: tuple[PoseSample, ...]
    actuator: tuple[ActuatorSample, ...]


@dataclass(frozen=True)
class Event:
    id: str
    detector: str
    stream: str
    t_start: float
    t_end: float
    magnitude: float
    unit: str
    held_gz: float | None = None


@dataclass(frozen=True)
class Flag:
    t: float
    seq: int
    stream: str
    detector: str
    code: str
    value: float
    t_host: float


@dataclass(frozen=True)
class ClockDriftWindow:
    t_host_end: float
    imu_end_seq: int
    delta: float | None
    identifiable: bool
    sse: float | None


class ParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class FaultScore:
    id: str
    detector: str
    outcome: Literal["TP", "FN"]
    latency_us: int | None
    latency_s: float | None
    t_flag_host: float | None
    n_flags: int


@dataclass
class FalsePositive:
    detector: str
    t_host: float
    seq: int


@dataclass
class Score:
    metric: str
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int
    faults: list[FaultScore]
    false_positives: list[FalsePositive]
