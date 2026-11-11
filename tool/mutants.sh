#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DETECT="$ROOT/field_telemetry_analyzer/detect.py"
export PYTHONPATH="$ROOT"

rm -rf "$ROOT/field_telemetry_analyzer/__pycache__" "$ROOT/tests/__pycache__"

backup="$(mktemp)"
cp "$DETECT" "$backup"
restore() { cp "$backup" "$DETECT"; rm -rf "$ROOT/field_telemetry_analyzer/__pycache__"; }
trap restore EXIT

mutant_run() {
  local node="$1"
  shift
  cp "$backup" "$DETECT"
  rm -rf "$ROOT/field_telemetry_analyzer/__pycache__"
  python3 - "$DETECT" "$@" <<'PY'
import sys
path, ops = sys.argv[1], sys.argv[2:]
text = open(path, encoding="utf-8").read()
for i in range(0, len(ops), 2):
    old, new = ops[i], ops[i + 1]
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"anchor {old!r} matched {count} times, want 1")
    text = text.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(text)
PY
  set +e
  log="$(pytest -q -rA "$node" 2>&1)"
  code=$?
  set -e
  if [[ "$code" -eq 0 ]]; then
    echo "expected failure: $node"
    echo "$log"
    exit 1
  fi
  if [[ "$code" -eq 2 || "$code" -eq 4 || "$code" -eq 5 ]]; then
    echo "bad pytest exit $code for $node"
    echo "$log"
    exit 1
  fi
  if ! grep -q "FAILED $node" <<<"$log"; then
    echo "missing FAILED line for $node"
    echo "$log"
    exit 1
  fi
  if ! grep -q "AssertionError" <<<"$log"; then
    echo "missing AssertionError for $node"
    echo "$log"
    exit 1
  fi
}

mutant_run tests/test_detect.py::test_latency_imu_bias \
  "IMU_BIAS_DELTA = 0.25" "IMU_BIAS_DELTA = 2.5"

mutant_run tests/test_detect.py::test_latency_gyro_dropout \
  "        nan_g = not np.isfinite(gx) or not np.isfinite(gy) or not np.isfinite(gz)" \
  $'        gx, gy, gz = np.nan_to_num(gx, nan=0.0), np.nan_to_num(gy, nan=0.0), np.nan_to_num(gz, nan=0.0)\n        nan_g = not np.isfinite(gx) or not np.isfinite(gy) or not np.isfinite(gz)'

mutant_run tests/test_detect.py::test_latency_stuck_sensor \
  "STUCK_VAR = 2.5e-7" "STUCK_VAR = -1.0"

mutant_run tests/test_detect.py::test_latency_timestamp_gap \
  "GAP_TH = 0.10" "GAP_TH = 10.0"

mutant_run tests/test_detect.py::test_latency_timestamp_jump \
  $'        if dt <= 0:\n            flags.append(\n                Flag(\n                    t=cur.t,\n                    seq=cur.seq,\n                    stream="pose",\n                    detector="timestamp_jump",' \
  $'        if dt < -1e9:\n            flags.append(\n                Flag(\n                    t=cur.t,\n                    seq=cur.seq,\n                    stream="pose",\n                    detector="timestamp_jump",'

mutant_run tests/test_detect.py::test_latency_actuator_sat \
  "SAT_DWELL_SAMPLES = 10" "SAT_DWELL_SAMPLES = 3600"

mutant_run tests/test_detect.py::test_latency_pose_jump \
  "POSE_V_MAX = 0.80" "POSE_V_MAX = 1e6"

mutant_run tests/test_detect.py::test_latency_clock_drift \
  "DRIFT_ABS = 0.08" "DRIFT_ABS = 10.0"

restore
trap - EXIT
rm -rf "$ROOT/field_telemetry_analyzer/__pycache__"
pytest -q \
  tests/test_detect.py::test_latency_imu_bias \
  tests/test_detect.py::test_latency_gyro_dropout \
  tests/test_detect.py::test_latency_stuck_sensor \
  tests/test_detect.py::test_latency_timestamp_gap \
  tests/test_detect.py::test_latency_timestamp_jump \
  tests/test_detect.py::test_latency_actuator_sat \
  tests/test_detect.py::test_latency_pose_jump \
  tests/test_detect.py::test_latency_clock_drift \
  tests/test_detect.py::test_standard_precision_recall
echo "mutants ok"
