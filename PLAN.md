# field-telemetry-analyzer — v1 plan

Checked 2026-11-10, then revised the same day after an independent review and a local prototype at seed `20261110`. Outbound license is **Apache-2.0**. Planning only; no public repo existed when this plan was frozen. `gh repo list applycoding --limit 200` has no `applycoding/field-telemetry-analyzer`.

## Goal

Public portfolio demo for Arpan Bom (idea #14): an **offline** analyzer for IMU, pose, and actuator logs. It parses logs, plots signals, raises simple explainable anomaly flags, scores those flags against injected ground truth, and writes a run report (HTML, Markdown, flags CSV, PNG plots).

This demo shows Python log parsing, IMU and pose plots, and a field-test-style report. It does not claim real field logs, production FDIR, ISO 26262, flight qualification, or any ML metric.

Git author and committer: **Arpan Bom <applycoding@gmail.com>**. No `Co-authored-by` or AI trailer. No AI credit in the README or commits.

Wording in README, REPORT text, and module docs: **"original implementation, inspired by"** well-known residual, windowed-statistic, and change-detection methods. Never "invented."

## Scope

Python package `field_telemetry_analyzer`, console script `fta`. File in, report out. No network and no telemetry. Every log used by the demo, tests, CI, and GitHub Pages is produced by `fta generate` (or `generate()`) from an explicit integer seed.

Differentiate existing applycoding work:

- `applycoding/robot-fleet-mqtt-telemetry` (public) is a live fleet pipeline: robots publish JSON over Mosquitto, ingestion writes TimescaleDB, threshold rules call a webhook, Grafana and REST read the tables. This repo does not use MQTT, TimescaleDB, Grafana, brokers, or live streaming.
- A private actuator power map for battery pitch exists elsewhere in applycoding. Do not copy it, and do not build an actuator-power or battery-pitch map here.
- `applycoding/rosbag-eval-bench` (in planning) is MCAP bag metric regression for planning, localization, and detection scores. This repo is not a bag eval bench, does not use MCAP, and does not score planners or detector mAP.
- `applycoding/teleop-console-demo` is browser teleop record/replay of control messages.
- `applycoding/react-ts-fleet-dashboard`, `ekf-gnss-localization`, `sim-gimbal-stabilizer`, and `flutter-robot-operator` are a dashboard, an estimator, a gimbal controller, and an operator UI. Do not reuse their code.

Reimplement parsers and detectors from first principles in Python and numpy. Do not vendor or copy tca, fault-detection toolkits, imu_tools, robot_localization, foxglove, PlotJuggler, or DiagnosticAggregator sources.

## Architecture

**Decision:** one kinematic truth, then seeded measurement noise, then eight explicit injections. Detectors read only the injected log. Scoring reads a sidecar the detectors never open. Reports render detector output and, when given, the sidecar.

**Why:** Interview readers can rerun one seed and match hashes. Event precision/recall plus exact latency fails a detector that sprays flags or that is late, which sample-level micro-P/R would hide. Keeping truth out of the log file is the difference between a scored fixture and a labeled dump.

### Clock, frames, noise

Seed `20261110`. Duration 60.00 s, half-open `[0, 60)`. Planar differential drive. Body x forward, y left, z up (REP-103-like). Pose is SE(2) in frame `map`: `x`, `y`, `yaw`. IMU is body. `g = 9.80665` m/s². At rest the specific force is `(0, 0, +g)` (ROS-common "az ≈ +g on a table").

| Stream | Rate | `dt` | Samples | `seq` |
| --- | --- | --- | --- | --- |
| IMU | 100 Hz | 0.01 s | 6000 | `0 .. 5999`, `t_true = seq * 0.01` |
| Pose | 50 Hz | 0.02 s | 3000 | `0 .. 2999`, host `t = seq * 0.02` |
| Actuator | 50 Hz | 0.02 s | 3000 | same grid as pose |

`v_max = 0.80` m/s, `omega_max = 1.20` rad/s, wheelbase `L = 0.30` m, actuator rail `u_max = 1.00` m/s (wheel linear speed). `u_l = v - ω L/2`, `u_r = v + ω L/2`.

Noise is `numpy.random.Generator(numpy.random.PCG64(seed))`, scalar `normal` draws, zero mean, independent per axis. Draw order: every IMU sample `(ax, ay, az, gx, gy, gz)`, then every pose sample `(x, y, yaw)`, then every actuator sample `(left_meas, right_meas)`, including pose rows that a later injection will drop. Sigmas: accel `0.02` m/s², gyro `0.005` rad/s, pose position `0.005` m, pose yaw `0.002` rad, actuator meas `0.01` m/s. Commands and timestamps are exact except injections. No `time.time` or `time.time_ns`. Same seed and same scenario name produce bit-identical CSV and JSONL.

Truth specific force and rate, sampled at `t_true`, before noise and injections: `ax = v̇`, `ay = v ω`, `az = g`, `gx = gy = 0`, `gz = ω`.

### Trajectory

Faults are measurement and timestamp injections. The pose/IMU truth path does not teleport, saturate, or drop out. `standard` and `clean` share this path and these noise draws. `clean` skips injections and does not write `ground_truth.json`.

| Interval | `v` (m/s) | `ω` (rad/s) | `v̇` | Role |
| --- | --- | --- | --- | --- |
| `[0, 5)` | 0 | 0 | 0 | rest |
| `[5, 8)` | `0.20 (t-5)` | 0 | 0.20 | accel that must not trip `imu_bias` |
| `[8, 16)` | 0.60 | 0 | 0 | cruise; F1 starts at 12.00 |
| `[16, 20)` | 0.60 | 0.40 | 0 | turn across the F4 hole |
| `[20, 28)` | 0.50 | 0 | 0 | cruise; F2 at 22; F6 injection at 26–27 |
| `[28, 36)` | 0.40 | 0.50 | 0 | turn; ends as F3 begins |
| `[36, 48)` | 0.40 | 0 | 0 | `ω` steps `0.50 → 0` at 36.00; F3, F7, F5 |
| `[48, 60)` | 0.30 | `0.30 sin(π(t-48)/2)` | 0 | weave, period 4 s, for F8 |

Yaw on the weave is the exact antiderivative `yaw(48) + (0.60/π) (1 - cos(π(t-48)/2))`. The generator integrates at the **100 Hz IMU grid** with constant-`v`, constant-`ω` arcs that use the interval-average `v` or `ω` (so yaw on analytic segments matches the closed form at `1e-12`). Pose and actuator rows are the even IMU samples (subsampled), not a separately integrated 50 Hz path. Position on the weave is that 100 Hz arc recurrence, not a Bessel integral of the sinusoid. Yaw is stored unwrapped (5.60 exceeds π); only differences are wrapped. Velocity steps at 8, 16, 20, 28, 36, and 48 s are idealized piecewise kinematics: `ax = v̇` does not include impulsive Dirac accelerations at those instants. Wheel commands on the table stay inside the rail (largest nominal `|u|` is `0.66` on `[16, 20)`). F6 overwrites the logged left command and measurement only.

### Eight faults

Host / true times. Magnitudes are exact. The log has no fault-label column. `ground_truth.json` is sidecar-only.

| id | detector | Injection | Host interval | Magnitude |
| --- | --- | --- | --- | --- |
| F1 | `imu_bias` | add to `ax` after noise | `[12.00, 60)` persists | `+0.40` m/s² |
| F2 | `gyro_dropout` | `gx, gy, gz` set to NaN; `t`, `seq`, accel kept | `[22.00, 22.50)` = 50 samples | 50 NaN triples |
| F3 | `stuck_sensor` | `gz` held, no noise | `[36.00, 37.50)` | hold `1.50` s |
| F4 | `timestamp_gap` | drop pose rows | first omitted `18.00`, next kept `18.40` | `Δt = 0.42` s from last kept `17.98` (seq `899` → `920`, 20 rows dropped, seq not renumbered) |
| F5 | `timestamp_jump` | one pose stamp rewritten | seq `2250` (host `45.00`) stamped `44.75` | stamp error `-0.25` s; `Δt` from `44.98` is `-0.23` s; next row seq `2251` stays `45.02` |
| F6 | `actuator_sat` | overwrite left channel | `[26.00, 27.00)` | `left_cmd = 1.20`, `left_meas = 1.00` exactly |
| F7 | `pose_jump` | add `+0.80` m to measured `x` | `[42.00, 42.20)` = 10 pose rows | snap back at the first unshifted row `42.20` |
| F8 | `clock_drift` | IMU stamp scale | `t_true >= 48` | `ρ = 0.02` |

F3 hold is the **noiseless** kinematic `gz` at `t = 35.99`, which is `0.50` rad/s, not a copy of the noisy sample. The step `ω: 0.50 → 0` at `36.00` is what makes a frozen gyro disagree with motion. F8, integer microseconds: `t_true_us = seq * 10000`; if `t_true_us >= 48_000_000` then `t_us = 48_000_000 + (t_true_us - 48_000_000) * 102 // 100`, else `t_us = t_true_us`. Offset at true `t = 60` is `0.24` s. Pose and actuator stamps stay on the host clock. `ρ = 0.02` is exaggerated so a 60 s file can show lag on a `0.01` s grid.

### Detectors

Deterministic, numpy only, no ML, no Kalman filter. A windowed flag is stamped at the **right edge** of the window that completed it. Samples inside a half-open window `[t-W, t)` do not include time `t`.

**`imu_bias`.** Same formula as a trailing-versus-leading mean on `ax` only: `Δ = mean(ax[t-W:t]) - mean(ax[t-2W:t-W])` with `W = 0.20` s (20 samples), `|Δ| >= 0.25` m/s². **Evaluate only at `t = k W` for integer `k >= 2`.** Non-finite `ax` in either block skips that edge. First flag at `t = 12.20` (`Δ = 0.40`). The 5–8 s accel produces `|Δ| = 0.20` at `t = 5.20` and `t = 8.20` and does not flag. Latency **`0.20` s**. A per-sample slide is rejected: with half-open `[t-0.20, t)`, the first 13-sample noiseless crossing is at `t = 12.13` (`0.40 * 13/20 = 0.26`), not 12.12. The 12-sample bin at 12.12 is `0.24`, about `1.58 σ` from the threshold (`σ_Δ = 0.02 √(2/20) ≈ 0.00632`). Block edges put the accel `0.05` under the gate (~`8 σ`) and the bias `0.15` over it.

**`gyro_dropout`.** Flag the first IMU sample where any of `gx, gy, gz` is non-finite, or where `Δt` between successive IMU **stamps** is `> 2.5 * 0.01` s. Standard fixture hits the NaN branch at `22.00`. Latency **`0.00` s**.

**`stuck_sensor`.** On a window of `W = 0.30` s (30 samples), every sample finite, population variance (`/ N`, numpy `ddof=0`) `< 2.5e-7`, **and** `max(gz) == min(gz)`, and the robot is not at rest: mean over actuator rows in that host window of `max(|left_meas|, |right_meas|) > 0.05`. The equality conjunct is what makes latency exact. A window that mixes the hold with the noisy sample at `t = 35.99` has variance `δ² * 29/900`, which sits under `2.5e-7` when `|δ| < √(2.5e-7 * 900/29) ≈ 0.002785` and would otherwise flag at `36.29`. Identical floats are the injected noiseless hold; ordinary gyro noise (`σ² = 2.5e-5`) is not identical. Actuator speed is the motion signal because a pose difference of `σ = 0.005` m is a poor speed estimate. If the noisy sample at `t = 35.99` is exactly the hold, the generator uses `held_gz = 0.51` instead of `0.50` and writes `held_gz` on the F3 sidecar object (no extra RNG draw). The first all-hold window is `[36.00, 36.30)`. Latency **`0.30` s**. The flag `seq` is the right-edge sample (`3630`), which is not inside the window.

**`timestamp_gap` vs `timestamp_jump`.** On successive kept pose rows:

- `timestamp_jump` iff `t_cur - t_prev <= 0`. Flag that row. Latency uses `t_host = seq * 0.02`, so F5 flags at host `45.00`. Latency **`0.00` s**.
- `timestamp_gap` iff `t_cur - t_prev > 0.10` **and** `seq_cur >= seq_prev + 2`. Flag the first row after the hole (`t = 18.40`). Latency **`0.40` s** from `t_start = 18.00`.
- A positive `Δt` with `seq_cur == seq_prev + 1` is neither. F5's recovery `44.75 → 45.02` is `Δt = 0.27 > 0.10` with seq `+1`, so it is not a gap and not a second jump. `pose_jump` ignores pairs with `Δt <= 0`.

**`actuator_sat`.** Flag at `t` when every actuator sample in `[t-D, t)`, `D = 0.20` s (10 samples), has `|left_meas|` or `|right_meas| >= u_max - 1e-9` on a matching side, and that same side has `|cmd| > u_max` on at least one sample in the dwell. First edge `t = 26.20`. Latency **`0.20` s**.

**`pose_jump`.** For monotonic pairs (`Δt > 0`), flag when `hypot(Δx, Δy) > v_max * Δt + 0.05`. Nominal `v_max * 0.02 + 0.05 = 0.066` m. The `+0.80` m step at `42.00` and the snap-back at `42.20` are two flags inside one F7 event. First-flag latency **`0.00` s**.

**`clock_drift`.** Does not use `t - seq * dt` as the statistic (that shortcut is an explicit non-goal). Sensitivity tests use a shifted-stamp fixture and must show the flag tracks signal alignment, not a seq-derived residual. Pose yaw-rate is a **two-point interval rate**, not a three-point centered difference: `wrap(yaw[k] - yaw[k-1]) / ((seq[k] - seq[k-1]) * 0.02)`, placed at the midpoint of the two **host** times (seq-derived; F5's rewritten stamp is not used as a midpoint). Skip pairs with `seq` gap `>= 2` (do not interpolate across F4). Both that rate and IMU `gz` get a causal trailing mean of nominally `0.20` s (10 pose rate samples, 20 finite IMU samples). A NaN gyro sample drops out of the IMU smoother and does not borrow later samples to fill a 20-count window across F2; the window is time-based on the stream's stamps and is invalid if it contains a non-finite value. This is an **offline** estimator: a lag query may read pose inside the same analysis window. The flag time is the window's right edge, a scheduled offline latency, not an online causal time.

Windows are **host-time** intervals `[t0, t1)` with length `5.00` s, stride `2.50` s, `t0 = 2.5 k`, `t1 = t0 + 5 <= 60`. IMU rows enter a window by host time `seq * 0.01`. A window is eligible when peak-to-peak of the smoothed pose rate is `>= 0.20` rad/s. On each eligible window, grid-search `δ` in `[-1.0, 1.0]` step `0.01` (201 points) minimizing SSE between smoothed `gz` and the smoothed pose rate interpolated at `t_imu - δ`, using only query points that lie inside the pose-rate support of that window (no endpoint clamping; require at least 10 pairs). Tie-break: smaller SSE, then smaller `|δ|`, then the negative value. Positive IMU stamp drift must produce **positive** `δ` in `pose_rate(t_imu - δ)`.

A window is **unidentifiable** (no `δ` published, cannot flag) if the minimizer sits on the grid edge `|δ| = 1.0`, or if it has fewer than 10 interpolation pairs. This quality gate is data-derived. It is what rejects the F3-poisoned windows on the standard log (those minimizers hit `δ = 1.0`); it is **not** a `midpoint >= 48` onset gate, which would have embedded the injected schedule in the detector. **Primary gate:** flag once, at the right edge of the first identifiable eligible window with `|δ| >= 0.08` s.

Prototype at seed `20261110`, plan draw order: standard identifiable `δ` after the weave begins is `0.02, 0.05, 0.09, 0.14, 0.19` on windows ending `50, 52.5, 55, 57.5, 60`. First gate hit is `[50.00, 55.00)`, `t_host = 55.00`, IMU seq `5500`, stream stamp `t = 55.14` (drifted), latency **`7.00` s** (`7000000` µs). This integer is now **frozen from that measurement**, not a prediction. Clean max identifiable `|δ|` is `0.01` s (eight grid steps below the gate). Mean-offset integrals (`0.0080, 0.0405, 0.0900, 0.1400, 0.1900`) describe the ramp, not the SSE minimizer; the measured bins are the contract.

### Scoring

One ground-truth event per F1–F8 on `standard`. A flag carries `t_host`: IMU `seq * 0.01` (not the drifted `t`), pose and actuator `seq * 0.02`. The F5 row keeps seq `2250`, so its host time stays `45.00`.

Greedy attribution, one detector id at a time: an event **absorbs every** flag of that detector with `t_host` in `[t_start, t_end + one sample]` (`0.01` s IMU, `0.02` s pose/actuator). Absorbed extras are not false positives. An event with at least one absorbed flag is a TP; with none, an FN. A flag that no event absorbs is an FP. `t_end` values: F1 `60`, F2 `22.50`, F3 `37.50`, F4 `18.40`, F5 `45.00`, F6 `27.00`, F7 `42.20`, F8 `60`.

`precision = tp / (tp + fp)` if the denominator is non-zero, else `1.0`. `recall = tp / (tp + fn)` if the denominator is non-zero, else `1.0`. On `standard`: **precision == 1.0 and recall == 1.0** (8 TP, 0 FP, 0 FN). On `clean`: **zero flags** (this is not a vacuous P/R check). Latency of a TP is `t_host(first absorbed flag) - t_start`, asserted as integer microseconds (`round(latency_s * 1e6)`), because binary64 cannot hold `0.20` exactly. Equality, not a minimum and not a cap.

| Fault | Latency | Microseconds |
| --- | --- | --- |
| F1 `imu_bias` | 0.20 s | 200000 |
| F2 `gyro_dropout` | 0.00 s | 0 |
| F3 `stuck_sensor` | 0.30 s | 300000 |
| F4 `timestamp_gap` | 0.40 s | 400000 |
| F5 `timestamp_jump` | 0.00 s | 0 |
| F6 `actuator_sat` | 0.20 s | 200000 |
| F7 `pose_jump` | 0.00 s | 0 |
| F8 `clock_drift` | 7.00 s predicted | 7000000 |

F8's latency is **frozen at `7000000` µs** from the seed-`20261110` prototype (first identifiable window with `|δ| >= 0.08` ends at host `55.00`). Clean-run max identifiable `|δ|` was `0.01` s. The test asserts those values. Do not retune the gate or the smoother against this seed.

`score.json` fields: `metric` (`event_attribution_v1`), `precision`, `recall`, `tp`, `fp`, `fn`, `faults[]` with `id`, `detector`, `outcome` (`TP` or `FN`), `latency_us` (JSON `null` if FN), `latency_s`, `t_flag_host`, `n_flags`, and `false_positives[]` with `detector`, `t_host`, `seq`. Strict JSON (`allow_nan=False`).

### Report and Pages

`fta report` writes `report.md`, `report.html`, `index.html` (same HTML), `flags.csv`, and PNGs at dpi `100`, backend `Agg`, fixed figure size: `imu.png` (accel and gyro, flag markers, truth bands when `--truth` is passed), `pose_path.png`, `pose_time.png`, `actuator.png`, `clock_offset.png` (per-window `δ`), `flags.png`. Optional `--truth` is how CI draws bands; the required CLI arguments stay `--log`, `--flags`, `--score`, `--out`. HTML `<title>` is `Field telemetry analyzer (synthetic data only)`. A visible banner reads `These are not real field logs.` `flags.csv` header is `t,seq,stream,detector,code,value,t_host` with `code == detector` in v1, rows sorted by `(t_host, stream, detector, seq)`.

The sample site is generated in CI from `standard` / seed `20261110`, not from a hand-edited HTML file. Playwright serves it with `http-server`, checks the title and the banner, and writes a screenshot at **exactly 1280×720** (`fullPage` off, `deviceScaleFactor: 1`, screenshot `scale: "css"`, no clip). Wait for images and fonts before capture. CI may upload that screenshot; it must not commit it. `docs/demo.png` is produced locally and checked in. Tests hash the canonical flag table and `score.json`, not PNG bytes. A PNG byte hash on ubuntu-24.04 is optional and is not a required gate (font rasterization).

## Pinned stack

Exact pins, verified 2026-11-10. CI does not float `latest`. First build writes hashed locks with `pip-compile --generate-hashes` (pip-tools). CI installs with `--require-hashes`.

- Python **3.12.16** on `ubuntu-24.04` (`python-version: "3.12.16"` for `actions/setup-python`). 3.12 is in security-only maintenance through October 2028. A developer machine with 3.13 is best-effort; no 3.13-only syntax. The tested matrix is 3.12.16 on ubuntu-24.04; do not claim broader support.
- Runtime: `numpy==2.5.4` (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; requires-python `>=3.12`), `matplotlib==3.11.2` (use the matplotlib license agreement from the distribution, not a generic PSF stand-in; requires-python `>=3.11`), `Jinja2==3.1.6` (record the clause count from the distribution license file at lock time; PyPI classifiers only say "BSD License"), `MarkupSafe==3.0.4` (BSD-3-Clause).
- Matplotlib lock transitives, confirm and license at lock time: contourpy, cycler, fonttools, kiwisolver, packaging, pillow, pyparsing, python-dateutil, six. `pillow==13.0.0` (MIT-CMU) is expected. Do not import Pillow; PNG width/height are read from the IHDR with the stdlib.
- Dev: `pytest==9.2.0` (MIT) and lock transitives `iniconfig==2.3.1` (MIT), `packaging==26.3` (Apache-2.0 OR BSD-2-Clause), `pluggy==1.7.0` (MIT), `pygments==2.21.0` (BSD-2-Clause), confirm at lock time. `ruff==0.17.4` (MIT). `pip-tools==7.6.2` (BSD-3-Clause).
- Node `24.22.2`, released 2026-10-28. Node 24 (Krypton) became LTS on **2025-10-28**, entered maintenance on 2026-10-20, and is supported through 2028-04-30. Node 26 is a newer LTS line; v1 stays on 24.22.2. `@playwright/test==1.65.0`, `http-server==14.1.1`. Commit `package-lock.json`. CI uses `npm ci` and installs the pinned Playwright Chromium.
- No pandas, scipy, scikit-learn, ROS, MCAP, PyYAML, or message bus. Workflow tests are string checks, not a YAML library.
- Actions, full SHAs, also listed in `.github/workflow-pins.md`:
  - `actions/checkout@v7.0.1` `3d3c42e5aac5ba805825da76410c181273ba90b1`
  - `actions/setup-python@v7.1.0` `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`
  - `actions/setup-node@v7.1.0` `949feb2413d6458794dcd2491c4babbbce0c15c1`
  - `actions/upload-artifact@v7.0.2` `cf430e030ddbb5b0abf93d22962f4752f3646cd9`
  - `actions/download-artifact@v8.0.2` `9000827ccba6bdab643e8b6fd33ac0654aef8333`
  - `actions/configure-pages@v6.0.0` `45bfe0192ca1faeb007ade9deae92b16b8254a0d`
  - `actions/upload-pages-artifact@v5.0.0` `fc324d3547104276b827a68afc52ff2a11cc49c9`
  - `actions/deploy-pages@v5.0.1` `368f82528645a54fb793d4d04e342629a3f51346`

Record `pip --version` from the first green 3.12 runner in NOTICE and pin that pip in CI afterward.

## File layout

```text
pyproject.toml                 # console script fta; requires-python >=3.12
requirements.txt               # runtime pins
requirements.lock.txt          # pip-compile --generate-hashes
requirements-dev.txt
requirements-dev.lock.txt
package.json                   # playwright, http-server
package-lock.json
field_telemetry_analyzer/
  cli.py  generate.py  kinematics.py  parse.py  detect.py  score.py  report.py
  templates/report.html.j2  templates/report.md.j2
tests/                         # test_generate, test_faults, test_detect, test_parse,
                               # test_score, test_report, test_guards
tool/mutants.sh  tool/notice_check.py  tool/spdx_check.py
docs/demo.png                  # 1280×720, committed from a local Playwright run
.github/workflows/ci.yml
.github/workflows/pages.yml
.github/workflow-pins.md
LICENSE  NOTICE  README.md  REFERENCES.md
```

## Interfaces

Dataclasses, floats as Python `float`, sequences as tuples:

- `ImuSample(t, seq, ax, ay, az, gx, gy, gz)`, `PoseSample(t, seq, x, y, yaw)`, `ActuatorSample(t, seq, left_cmd, right_cmd, left_meas, right_meas)`, `RunLog(imu, pose, actuator)`.
- `Event(id, detector, stream, t_start, t_end, magnitude, unit, held_gz=None)` — `held_gz` is set only on F3 and is written on the sidecar.
- `Flag(t, seq, stream, detector, code, value, t_host)`.
- `ParseError(code: str, message: str)` subclasses `Exception`. Codes: `missing_column`, `invalid_timestamp`, `empty_log`, `invalid_json`, `unknown_topic`, `invalid_field`.
- `Score` as in the `score.json` fields above.

Functions:

- `generate(scenario: Literal["standard","clean"], seed: int) -> tuple[RunLog, tuple[Event, ...]]` — clean returns an empty event tuple.
- `write_run(log, events, out_dir) -> None` — CSV, JSONL, and `ground_truth.json` only when `events` is non-empty.
- `parse_csv_dir(path) -> RunLog`, `parse_jsonl(path) -> RunLog`.
- `detect(log, disable: Collection[str] = ()) -> list[Flag]`. Unknown name raises `ValueError`; the CLI maps that to exit 2.
- `score(flags, events) -> Score`.
- `write_report(log, flags, score, out_dir, truth=None) -> None`.

CSV headers, one stream per file, seq order, `\n` newlines: `imu.csv` `t,seq,ax,ay,az,gx,gy,gz`; `pose.csv` `t,seq,x,y,yaw`; `actuator.csv` `t,seq,left_cmd,right_cmd,left_meas,right_meas`. Timestamps are integer microseconds rendered with 6 decimal places. Other floats use `format(x, ".17g")`. NaN is the token `nan`. Gyro may be NaN; a NaN timestamp, accel, pose field, or actuator field is `invalid_field` on the way in (the generator is the only writer of gyro NaNs).

JSONL, one object per line. Gyro dropouts are encoded as the JSON token `NaN` (Python `json` with `allow_nan=True`; not strict RFC 8259; **not** the lowercase CSV token `nan`). The parser accepts `NaN`, `Infinity` is rejected as `invalid_field`, and only `gx, gy, gz` may be non-finite. Sidecar, `score.json`, and the HTML/Markdown reports are strict JSON (`allow_nan=False`). Envelope `{"t", "seq", "topic", "type", "data"}`. Topics: `/imu/data` type `Imu`, `/pose` type `Pose`, `/actuator` type `Actuator`. `data` keys match the CSV measurement columns. Sort key when writing: `(t_host, stream_rank)` with IMU `0`, pose `1`, actuator `2`. `detect` defaults to CSV when `imu.csv` is present; `--format jsonl` selects `log.jsonl`. It does not open `ground_truth.json`.

Parser failures: missing required column `missing_column`; non-numeric, NaN, or infinite `t` is always `invalid_timestamp` (not `invalid_field`); empty file, header only, or whitespace-only JSONL `empty_log`; truncated or non-JSON line `invalid_json`; topic not in the three names `unknown_topic`; missing `data` field, extra CSV column, duplicate or non-increasing `seq` per stream, a string where a float is required, or `Infinity` in a data field `invalid_field`. Seq must increase; measurement stamps are not required to be monotonic (F5). Any of these aborts with no successful score file. Writing into a nonempty `--out` directory is rejected (exit 2) so a clean run cannot leave a stale `ground_truth.json` or `score.json`.

CLI, stdlib `argparse`:

- `fta generate --scenario standard|clean --seed 20261110 --out DIR`
- `fta detect --log DIR --out DIR [--format csv|jsonl] [--disable DETECTOR ...]`
- `fta score --log DIR --truth FILE --flags FILE --out score.json [--gate]`
- `fta report --log DIR --flags FILE --score FILE --out DIR [--truth FILE]`

Exit 0 after a successful parse and the command's normal write. `fta detect` exits 0 when flags exist. `fta score --gate` exits 1 when the event-attribution counts are not a perfect standard result, or when a clean/empty-truth run has any flag. Exit 2 on parse errors and usage errors. Parse errors print one line on stderr; argparse usage errors may include the usage block. Unknown `--disable` names fail with exit 2 before writing results.

## Edge cases

- Block `imu_bias` at `5.20` and `8.20` stays under `0.25` (prototype: `0.209574` and `-0.197403` at seed `20261110`). Later bias blocks have `Δ ≈ 0` and do not flag again. An off-grid bias step that splits a 0.20 s block with post-step fraction `f` in `[0.375, 0.625]` can miss completely (`0.40f` and `0.40(1-f)` both `< 0.25`). That limitation is disclosed; this fixture aligns F1 on a block edge on purpose.
- A stuck window that contains a non-finite gyro does not flag. F2 must not create an F3 flag.
- Rest (`[0, 5)`) does not flag `stuck_sensor`. The clean weave may estimate a small `δ`; it must stay below `0.08` s.
- F4 is a gap only. F5 is a jump only. The `0.27` s recovery is neither, and it is not a `pose_jump` (`0.27 * 0.80 + 0.05 = 0.266` m, while the robot moves about `0.008` m).
- Both F7 discontinuities attribute to F7. Flags of one detector inside its event window are not FPs.
- `clock_drift` drops non-finite `gz` and does not run the lag fit on ineligible (low excitation) windows, so straight-line segments cannot win an arbitrary `δ`.
- Malformed input never writes a `score.json` with `precision == 1`. Disabling an unknown detector is exit 2.
- Two `generate` calls match sha256. Tests do not compare wall-clock timestamps.

## Test plan

Pytest on the library, no network, no skips.

- `test_generate_bit_identical`: two `standard` writes and two `clean` writes in the same process/environment, sha256 of each CSV and of `log.jsonl`. A second seed differs. Unfaulted samples of `standard` equal `clean` exactly, including pose rows that F4 later drops (compare before the drop, and compare kept rows). This is in-environment repeatability, not a cross-platform golden hash (NumPy's PCG64 stream is also sensitive to the exact scalar `normal` call sequence; do not vectorize those draws).
- `test_kinematic_checkpoints`: truth pose at `t = 8, 16, 20, 36, 48` matches the closed forms in Verification hints within `1e-12`. Weave yaw at `t = 50` matches `yaw(48) + 1.2/π`.
- `test_fault_injections`: F1 step, 50 NaN gyros, F3 constant `gz` equal to sidecar `held_gz` and the sample at `35.99` unequal to it, F4 seq hole of 20 and stamp delta `420000` µs, F5 stamp `44.75` with seq `2250`, F6 command/meas, F7 `+0.80` on ten rows and the `42.20` snap-back, F8 integer stamp formula including the `0.24` s offset at true 60 s.
- `test_standard_precision_recall`, `test_latency_<detector>` for all eight, `test_clean_zero_flags`.
- `test_disable_<detector>`: eight tests, `detect(..., disable={that id})`, that event is FN, so recall is not 1. The public CLI flag is covered once (`fta detect --disable imu_bias`).
- `test_csv_jsonl_roundtrip`: generate, parse both, field-wise equality with NaNs equal.
- `test_parse_<code>`: one fixture per code listed above, exit 2 from the CLI, `ParseError.code` exact, no passing score.
- `test_timestamp_disambiguation`: recovery row produces no `timestamp_gap` and no second `timestamp_jump`.
- `test_report_artifacts`: required files exist; title and banner strings; `flags.csv` header; IHDR of a Playwright (or local) PNG is 1280×720.
- `test_scope_guards`: source and README contain `original implementation, inspired by`; they do not contain the word `invented`; imports do not include mqtt, sqlalchemy, psycopg, grafana client libraries, pandas, scipy, sklearn, rclpy, mcap, or a learning library. Workflow files contain no `continue-on-error`. Tests contain no `pytest.skip`, `pytest.xfail`, or `assert True`.

`tool/mutants.sh` (lesson from the flutter operator demo: the mutant must be collected and fail its targeted assertion, not fail to compile, fail collection, or skip the test). For each item, replace exactly one assignment, run only the named node id, require that the node was collected and executed and that it failed on an assertion about that detector (missing TP or wrong `latency_us`), restore the original bytes in `finally` (including on signals), re-run the unmodified baseline once at the end, and exit non-zero if the pattern did not match once, if pytest never ran the node, or if the target passed. A mutant that only fails some other test, or that fails at collection, is a failed job. Clear stale bytecode.

| Mutant | Edit | Targeted test |
| --- | --- | --- |
| M1 | `IMU_BIAS_DELTA = 0.25` → `2.5` | `test_latency_imu_bias` |
| M2 | in `detect_gyro_dropout` only, the assignment `nan_g = not np.isfinite(gx)` (or the locked equivalent) is preceded by `gx = gy = gz = np.nan_to_num(..., nan=0.0)` on a local copy, so the NaN branch never sees F2 | `test_latency_gyro_dropout` |
| M3 | `STUCK_VAR = 2.5e-7` → `-1.0` (`var < -1` never holds) | `test_latency_stuck_sensor` |
| M4 | `GAP_TH = 0.10` → `10.0` | `test_latency_timestamp_gap` |
| M5 | jump condition `dt <= 0` → `dt < -1e9` | `test_latency_timestamp_jump` |
| M6 | `SAT_DWELL = 0.20` → `3600.0` | `test_latency_actuator_sat` |
| M7 | detector `POSE_V_MAX = 0.80` → `1e6` (generator `v_max` untouched) | `test_latency_pose_jump` |
| M8 | `DRIFT_ABS = 0.08` → `10.0` | `test_latency_clock_drift` |

## Numbered success criteria

1. README, `report.html` `<title>`, the visible banner, and the Pages smoke all say these are synthetic data and not real field logs. Checked by `test_report_artifacts` and the `pages.yml` curl (`synthetic data`, case-insensitive).
2. `fta generate --scenario standard --seed 20261110` is bit-identical across two runs (CSV and JSONL sha256). `test_generate_bit_identical`.
3. The standard log contains all eight injections at the times and magnitudes in the fault table, and the sidecar matches those events. `test_fault_injections`.
4. `test_standard_precision_recall`: 8 TP, 0 FP, 0 FN, precision 1.0, recall 1.0.
5. `test_latency_<detector>` asserts the microsecond table, including F8 at `7000000`. Equality on `latency_us`, not a bound.
6. `test_clean_zero_flags`: the clean seed-`20261110` log produces an empty flag list.
7. `test_disable_<detector>`: each of the eight `--disable` / `disable=` switches turns that fault into an FN so criterion 4 would fail. No skipped tests.
8. `tool/mutants.sh`: each of M1–M8 fails its targeted test and is restored. The unmodified tree passes.
9. `test_csv_jsonl_roundtrip` plus `test_parse_missing_column`, `test_parse_invalid_timestamp`, `test_parse_empty_log`, `test_parse_invalid_json`, `test_parse_unknown_topic`, `test_parse_invalid_field`: exact `ParseError.code`, CLI exit 2, no successful score.
10. CI job `report` generates `report.md`, `report.html`, `flags.csv`, and the six PNGs from the standard fixture and uploads that directory. `test_report_artifacts` checks the set.
11. `pages.yml` deploys only after `ci.yml` succeeds on `main`, downloads the artifact by `github.event.workflow_run.id`, and the smoke (at least 12 tries, 10 s apart) gets HTTP 200 and `synthetic data`. No manual bypass. Static check in `test_scope_guards` for `workflow_run`, `branches: [main]`, and the permission block.
12. `tool/notice_check.py` exits 0 only when every lockfile distribution and every pinned dev tool is named with its version and a non-blank license, and NOTICE points at `REFERENCES.md` for idea-only credits.
13. `tool/spdx_check.py`: every authored `.py`, `.sh`, workflow YAML, and both Jinja templates starts with `SPDX-License-Identifier: Apache-2.0` in a comment the format allows (after a shebang if present).
14. `test_license_bytes`: `LICENSE` is 11358 bytes and sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
15. `test_scope_guards`: no MQTT, TimescaleDB, Grafana, ROS, MCAP, pandas, scipy, or scikit-learn imports or CI services; no ML detector. The phrase `original implementation, inspired by` is present in README. A wording ban on `invented` scans authored documentation and comments, with an allow-list for the sentence that forbids the word, so the guard does not self-match.
16. `test_scope_guards` also rejects `pytest.skip`, `pytest.xfail`, `assert True`, `continue-on-error`, and workflow jobs whose run step is only `echo`.
17. `test_kinematic_checkpoints` and `test_timestamp_disambiguation` match the locked trajectory and the gap/jump rule.
18. `docs/demo.png` IHDR is 1280×720 (`test_report_artifacts`). Playwright in job `e2e` repeats the title, banner, and dimension checks against the CI-generated report.
19. `test_generate_bit_identical` and a grep test `test_no_wall_clock` find no `time.time` or `time.time_ns` under the package. Flag-table and `score.json` bytes are stable; PNG bytes are not the hash gate.
20. After the repo exists, `git log --format='%an <%ae> | %cn <%ce>%n%b'` shows only `Arpan Bom <applycoding@gmail.com>` as author and committer, with no `Co-authored-by` and no AI trailer.

## Out of scope

Live streaming, MQTT, databases, Grafana, brokers, ROS, rosbag, and MCAP readers. Real, customer, or Harmattan logs. ML or learned detectors. 3D IMU mechanization beyond planar SE(2) plus specific force. Multi-robot fleets. A battery or actuator-power map. A web app beyond the static report. Certification claims (ISO 26262, flight qualification, production FDIR). Using `t - seq * dt` as the clock-drift statistic. Sample-level micro-P/R. Vendoring tca, imu_tools, robot_localization, foxglove, PlotJuggler, or DiagnosticAggregator.

## Documentation and honesty

README order: what it is (offline synthetic IMU/pose/actuator analyzer and run report); what it is not (not real field logs, not a live MQTT/Timescale/Grafana dashboard, not a battery or actuator-power map, not a bag-metric regression bench, not an ML detector, not anyone else's field software); generate / detect / score / report with one copy-paste command using seed `20261110`; Python 3.12 and the pins; honest limits. Those limits state that `ρ = 0.02` is a demo exaggeration, that block-aligned `imu_bias` will not see a `0.20` m/s² accel, that `stuck_sensor` requires a noiseless hold plus motion, that the lag fit is a 1-D grid not a filter, and that PNG bytes are not a portability hash.

`REFERENCES.md` is idea-only credits: textbook trailing-window and residual change detection, ordinary gap and monotonicity checks, cross-correlation delay estimation as the idea behind the lag grid, ROS `sensor_msgs/Imu` field naming, REP-103 axis conventions, matplotlib as the plotting tool. Name each project and its license. Say "inspired by" and "original implementation." Do not cite the private titan-logs repo. Do not copy code from those projects.

## License

Apache-2.0, not MIT. `LICENSE` is the verbatim file at `https://www.apache.org/licenses/LICENSE-2.0.txt` (11358 bytes, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`). `NOTICE` starts with the line `field-telemetry-analyzer, Copyright 2026 Arpan Bom`. It lists every direct and lockfile-transitive dependency and the pinned dev tools (Python 3.12, pip, pip-tools, ruff, pytest and its lockfile deps, Node, Playwright, http-server, each GitHub Action pin) with versions and licenses, and it points at `REFERENCES.md` for idea-only credits. Copyright year 2026, Arpan Bom. SPDX on authored sources as in criterion 13. Lockfiles are not re-licensed.

## Build and CI

`ci.yml` on `push` and `pull_request`, `ubuntu-24.04`, Python 3.12, Node `24.22.2`. Jobs, all required, no `continue-on-error`:

- `lint`: `ruff check`.
- `test`: `pytest` including the guard tests and `tool/notice_check.py` plus `tool/spdx_check.py`.
- `mutants`: `tool/mutants.sh`.
- `report`: `fta generate` standard seed `20261110`, `detect`, `score --gate`, `report --truth`, upload artifact `pages-site` (the HTML, CSV, and PNGs).
- `e2e`: download that artifact, `http-server`, Playwright Chromium, title and banner, screenshot dimensions 1280×720.

`pages.yml`: `workflow_run` on workflow `ci` completed, `branches: [main]`, `types: [completed]`. The deploy job `if` requires `github.event.workflow_run.conclusion == 'success'`, upstream event `push`, branch `main`, and the same repository. Download the CI artifact `pages-site` with `run-id: ${{ github.event.workflow_run.id }}` (not "latest") and `actions: read`. Repackage that directory and upload it with `actions/upload-pages-artifact` under the conventional name `github-pages` (distinct from `pages-site`); `deploy-pages` consumes `github-pages`. `permissions: { pages: write, id-token: write, actions: read, contents: read }`. Use the `github-pages` environment. Reject a stale successful `main` run whose head SHA is older than the latest `main`. Then curl the Pages URL until HTTP 200 and the substring `synthetic data` (case-insensitive) succeed, at most 12 tries, 10 s apart, with a request timeout; stop on the first success. No `workflow_dispatch` in v1. Do not execute artifact-provided scripts.

## Risks

- F3 poisons lag estimates in windows `[32.50, 37.50)` and `[35.00, 40.00)` on the standard log (prototype minimizers sat on the grid edge `δ = 1.0`). Those windows are unidentifiable under the quality gate and must not flag. Do not re-introduce a `midpoint >= 48` onset gate to hide that. If a future seed produces an identifiable `|δ| >= 0.08` before 48 s, that is a real FP and the quality gate or fixture must be revised — not the assertion loosened.
- Clean-run weave windows are excited. Eight grid steps separate `0` from `0.08`. The prototype measured max identifiable `|δ| = 0.01` s on clean at seed `20261110`.
- Pose-rate noise from yaw `σ = 0.002` over `0.02` s is large before smoothing (`≈ 0.14` rad/s). The `0.20` s trailing mean is part of the detector for that reason. IMU `gz` noise is `0.005` and is not the fragile term.
- Block alignment is a fixture limitation, not a universal change detector. A step that splits a block with post-step fraction in `[0.375, 0.625]` can be missed entirely. The README says so. F1 is aligned on a block edge on purpose.
- `json` NaN tokens are not strict JSON. The parser is Python's `json.loads`. Document that next to the JSONL schema.
- Matplotlib PNG bytes can change with the FreeType package on the runner. Hash flags and `score.json` only.
- Deleting only the `var < STUCK_VAR` conjunct, and leaving `max == min`, still flags the noiseless hold at `36.30` s, so the latency test stays green. That edit is not M3. M3 sets `STUCK_VAR` to `-1.0`, and `var < -1` fails on the hold. `mutants.sh` must apply that assignment.
- numpy's PCG64 stream is pinned by `numpy==2.5.4`. A numpy bump requires a deliberate hash refresh.

## Verification hints

Arithmetic below is closed form. A scratch prototype (`_proto/prototype.py`, not product code) was run on 2026-11-10 at seed `20261110` with the locked scalar draw order, under CPython 3.13.5 and `numpy==2.5.4`. It is evidence for the numeric gates, not a substitute for the CI suite on Python 3.12.16.

Truth pose before noise, arc recurrence:

- `t = 8`: `v = 0.60`, `x = 0.90`, `y = 0`, `yaw = 0`.
- `t = 16`: `x = 5.70`, `y = 0`, `yaw = 0`.
- `t = 20`: `yaw = 1.60`, `x = 5.70 + 1.50 sin(1.60)`, `y = 1.50 (1 - cos(1.60))` → `x ≈ 7.199360404562`, `y ≈ 1.543799283452`.
- `t = 36`: `yaw = 5.60`, `x ≈ 5.777890122626`, `y ≈ 4.898281374969`.
- `t = 48`: `yaw = 5.60`, `x ≈ 9.500606339475`, `y ≈ 1.868201513182`.
- Weave `yaw(t) = 5.60 + (0.60/π) (1 - cos(π(t-48)/2))`. At `t = 50`, `yaw = 5.60 + 1.2/π`. At `t = 52, 56, 60`, yaw has returned to `5.60`. `ω(t) = 0.30 sin(π(t-48)/2)` is not constant on `[48, 60)`.

`imu_bias` noiseless block `Δ`: accel edges `±0.20`, bias edge at `12.20` is `+0.40`. Rejected per-sample first 13-sample crossing is `t = 12.13`; the 12-sample bin at `12.12` is `0.24`. `σ_Δ ≈ 0.006324555`.

`stuck_sensor`: mixed window `[35.99, 36.29)` has population variance `δ² * 29/900`. That is `< 2.5e-7` when `|δ| < ≈ 0.002785`, which is why `max == min` is required. The pure hold `[36.00, 36.30)` has variance `0` and identical samples. Flag host time `36.30`, latency `0.30` s. The prototype prints the noise draw at seq `3599` and `held_gz`.

`pose_jump` threshold at `Δt = 0.02` is `0.066` m. F7 step is `0.80` m.

F8 mean-offset integrals `ρ ∫_{t0}^{t1} max(t-48, 0) dt / 5` with `ρ = 0.02`: `0.0080`, `0.0405`, `0.0900`, `0.1400`, `0.1900` on midpoints `47.5, 50.0, 52.5, 55.0, 57.5`. Prototype SSE bins on standard: `0.02, 0.05, 0.09, 0.14, 0.19`. Grid-edge rejects at mid `35.00` and `37.50` (`δ = 1.0`) because of F3. First `|δ| >= 0.08` is `[50.00, 55.00)`, flag `t_host = 55.00`, stream stamp `55.14`, latency `7.00` s. Clean max identifiable `|δ| = 0.01`. Accel-block prototype `Δ`: `0.209574` at 5.20, `-0.197403` at 8.20, `0.392092` at 12.20. `held_gz` stayed `0.50` (noisy `gz[3599] = 0.495…`). Bit-identical repeat writes of the three CSVs succeeded in-process.

Stamp check: `t_true = 60` s → offset `12_000_000 * 102 // 100 = 12_240_000` µs = `0.24` s. Last stored IMU seq `5999` has true time `59.99` s.

Measured prototype score on `standard`: 8 TP, 0 FP, 0 FN, latencies `(0.20, 0.00, 0.30, 0.40, 0.00, 0.20, 0.00, 7.00)` s (`latency_us` `200000, 0, 300000, 400000, 0, 200000, 0, 7000000`). Clean flag count `0`. All eight disable-switches produced a FN. PNG byte hashing stays off the required gate.
