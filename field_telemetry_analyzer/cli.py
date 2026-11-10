# SPDX-License-Identifier: Apache-2.0
"""Console entry point for the field telemetry analyzer."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from field_telemetry_analyzer.detect import detect
from field_telemetry_analyzer.generate import generate, write_run
from field_telemetry_analyzer.models import FalsePositive, FaultScore, Flag, ParseError, Score
from field_telemetry_analyzer.parse import parse_csv_dir, parse_jsonl
from field_telemetry_analyzer.report import write_report
from field_telemetry_analyzer.score import load_events, score, write_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fta")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--scenario", choices=("standard", "clean"), required=True)
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out", required=True)

    d = sub.add_parser("detect")
    d.add_argument("--log", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    d.add_argument("--disable", action="append", default=[])

    s = sub.add_parser("score")
    s.add_argument("--log", required=True)
    s.add_argument("--truth", required=True)
    s.add_argument("--flags", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--gate", action="store_true")

    r = sub.add_parser("report")
    r.add_argument("--log", required=True)
    r.add_argument("--flags", required=True)
    r.add_argument("--score", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--truth")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "generate":
            return _cmd_generate(args)
        if args.cmd == "detect":
            return _cmd_detect(args)
        if args.cmd == "score":
            return _cmd_score(args)
        return _cmd_report(args)
    except ParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _reject_nonempty_out(path: str) -> None:
    p = Path(path)
    if p.exists() and any(p.iterdir()):
        raise ValueError("output directory must be empty")


def _cmd_generate(args: argparse.Namespace) -> int:
    _reject_nonempty_out(args.out)
    log, events = generate(args.scenario, args.seed)
    write_run(log, events, args.out)
    return 0


def _load_log(log_dir: str, fmt: str):
    base = Path(log_dir)
    if fmt == "jsonl" or (fmt == "csv" and not (base / "imu.csv").exists()):
        jl = base / "log.jsonl"
        if jl.exists():
            return parse_jsonl(jl)
    if (base / "imu.csv").exists():
        return parse_csv_dir(base)
    return parse_jsonl(base / "log.jsonl")


def _cmd_detect(args: argparse.Namespace) -> int:
    _reject_nonempty_out(args.out)
    fmt = args.format
    if fmt == "csv" and (Path(args.log) / "imu.csv").exists():
        log = parse_csv_dir(args.log)
    elif fmt == "jsonl":
        log = parse_jsonl(Path(args.log) / "log.jsonl")
    else:
        log = parse_csv_dir(args.log)
    flags = detect(log, disable=args.disable)
    os.makedirs(args.out, exist_ok=True)
    _write_flags_csv(Path(args.out) / "flags.csv", flags)
    return 0


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


def _read_flags(path: str) -> list[Flag]:
    out: list[Flag] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                Flag(
                    t=float(row["t"]),
                    seq=int(row["seq"]),
                    stream=row["stream"],
                    detector=row["detector"],
                    code=row["code"],
                    value=float(row["value"]),
                    t_host=float(row["t_host"]),
                )
            )
    return out


def _cmd_score(args: argparse.Namespace) -> int:
    flags = _read_flags(args.flags)
    events = load_events(args.truth)
    sc = score(flags, events)
    write_score(sc, args.out)
    if args.gate:
        if not events and flags:
            return 1
        if events and (sc.tp != 8 or sc.fp != 0 or sc.fn != 0):
            return 1
        if events and len(events) < 8 and flags:
            return 1
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    import json

    _reject_nonempty_out(args.out)
    if (Path(args.log) / "imu.csv").exists():
        log = parse_csv_dir(args.log)
    else:
        log = parse_jsonl(Path(args.log) / "log.jsonl")
    flags = _read_flags(args.flags)
    sc_data = json.loads(Path(args.score).read_text(encoding="utf-8"))
    sc = Score(
        metric=sc_data["metric"],
        precision=sc_data["precision"],
        recall=sc_data["recall"],
        tp=sc_data["tp"],
        fp=sc_data["fp"],
        fn=sc_data["fn"],
        faults=[FaultScore(**{**f, "latency_us": f["latency_us"]}) for f in sc_data["faults"]],
        false_positives=[FalsePositive(**fp) for fp in sc_data["false_positives"]],
    )
    truth = load_events(args.truth) if args.truth else None
    write_report(log, flags, sc, args.out, truth=truth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
