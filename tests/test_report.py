# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import struct
import tempfile
from pathlib import Path

from field_telemetry_analyzer.detect import detect
from field_telemetry_analyzer.report import BANNER, TITLE, write_report
from field_telemetry_analyzer.score import score

SEED = 20261110


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not png")
    struct.unpack(">I", data[8:12])[0]
    ctype = data[12:16]
    assert ctype == b"IHDR"
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def test_report_artifacts(standard_log) -> None:
    log, events = standard_log
    flags = detect(log)
    sc = score(flags, events)
    with tempfile.TemporaryDirectory() as d:
        write_report(log, flags, sc, d, truth=events)
        out = Path(d)
        for name in (
            "report.md",
            "report.html",
            "index.html",
            "flags.csv",
            "imu.png",
            "pose_path.png",
            "pose_time.png",
            "actuator.png",
            "clock_offset.png",
            "flags.png",
        ):
            assert (out / name).is_file()
        html = (out / "report.html").read_text(encoding="utf-8")
        assert f"<title>{TITLE}</title>" in html
        assert BANNER in html
        with (out / "flags.csv").open(encoding="utf-8") as fh:
            header = fh.readline().strip()
        assert header == "t,seq,stream,detector,code,value,t_host"
    demo = Path(__file__).resolve().parents[1] / "docs" / "demo.png"
    assert demo.is_file()
    w, h = _png_size(demo)
    assert w == 1280
    assert h == 720
