# SPDX-License-Identifier: Apache-2.0
"""Event-attribution scoring against injected ground truth."""
from __future__ import annotations

import json
from pathlib import Path

from field_telemetry_analyzer.models import Event, FalsePositive, FaultScore, Flag, Score

SAMPLE_DT = {"imu": 0.01, "pose": 0.02, "actuator": 0.02}


def load_events(path: str | Path) -> tuple[Event, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    events: list[Event] = []
    for item in data:
        events.append(
            Event(
                id=item["id"],
                detector=item["detector"],
                stream=item["stream"],
                t_start=item["t_start"],
                t_end=item["t_end"],
                magnitude=item["magnitude"],
                unit=item["unit"],
                held_gz=item.get("held_gz"),
            )
        )
    return tuple(events)


def score(flags: list[Flag], events: tuple[Event, ...]) -> Score:
    absorbed_ids: set[int] = set()
    fault_rows: list[FaultScore] = []
    tp = fn = 0

    {id(f): f for f in flags}

    for ev in events:
        dt = SAMPLE_DT.get(ev.stream, 0.01)
        window_end = ev.t_end + dt
        absorbed = [
            f
            for f in flags
            if f.detector == ev.detector and ev.t_start <= f.t_host <= window_end
        ]
        for f in absorbed:
            absorbed_ids.add(id(f))
        if absorbed:
            first = min(absorbed, key=lambda f: f.t_host)
            latency_s = first.t_host - ev.t_start
            latency_us = round(latency_s * 1e6)
            fault_rows.append(
                FaultScore(
                    id=ev.id,
                    detector=ev.detector,
                    outcome="TP",
                    latency_us=latency_us,
                    latency_s=latency_s,
                    t_flag_host=first.t_host,
                    n_flags=len(absorbed),
                )
            )
            tp += 1
        else:
            fault_rows.append(
                FaultScore(
                    id=ev.id,
                    detector=ev.detector,
                    outcome="FN",
                    latency_us=None,
                    latency_s=None,
                    t_flag_host=None,
                    n_flags=0,
                )
            )
            fn += 1

    false_positives: list[FalsePositive] = []
    for f in flags:
        if id(f) not in absorbed_ids:
            false_positives.append(
                FalsePositive(detector=f.detector, t_host=f.t_host, seq=f.seq)
            )
    fp = len(false_positives)

    denom_p = tp + fp
    denom_r = tp + fn
    precision = tp / denom_p if denom_p else 1.0
    recall = tp / denom_r if denom_r else 1.0

    return Score(
        metric="event_attribution_v1",
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        fn=fn,
        faults=fault_rows,
        false_positives=false_positives,
    )


def write_score(score: Score, path: str | Path) -> None:
    obj = {
        "metric": score.metric,
        "precision": score.precision,
        "recall": score.recall,
        "tp": score.tp,
        "fp": score.fp,
        "fn": score.fn,
        "faults": [
            {
                "id": f.id,
                "detector": f.detector,
                "outcome": f.outcome,
                "latency_us": f.latency_us,
                "latency_s": f.latency_s,
                "t_flag_host": f.t_flag_host,
                "n_flags": f.n_flags,
            }
            for f in score.faults
        ],
        "false_positives": [
            {"detector": fp.detector, "t_host": fp.t_host, "seq": fp.seq}
            for fp in score.false_positives
        ],
    }
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")
