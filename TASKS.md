# Build tasks — field-telemetry-analyzer

Execute in order. Follow PLAN.md. Deviate only if a pin or a test proves a step broken, and record why in the PR or a short `DEVIATIONS.md`. **Never weaken a test** to make CI green. License is **Apache-2.0**, not MIT. Commit author and committer are always **Arpan Bom <applycoding@gmail.com>**. No AI credit anywhere in the repository or commit messages.

Each task has acceptance checks. A task is done only when those checks pass.

## 1. Repository skeleton and license

- Create the tree in PLAN.md.
- Confirm `LICENSE` is byte-identical to `https://www.apache.org/licenses/LICENSE-2.0.txt` (11358 bytes, sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`), including the appendix, with no line-ending normalization.
- Write `NOTICE` starting with `field-telemetry-analyzer, Copyright 2026 Arpan Bom`, a pointer that idea-only credits live in `REFERENCES.md`, and a dependency section to be filled when locks land.
- Keep the README's honesty labels: synthetic data only, not real field logs.
- `pyproject.toml` for package `field_telemetry_analyzer`, console script `fta`, `requires-python = ">=3.12"`, pinned runtime deps as in PLAN.md. pytest and ruff as dev extras.
- Add `SPDX-License-Identifier: Apache-2.0` on every authored source file from here on (after a shebang if present; Jinja comments in templates, `#` in workflows).

**Accept:** `cmp LICENSE` against a fresh curl of the official text exits 0. `pip install -e .` exposes `fta --help`. NOTICE points at REFERENCES.md.

## 2. Hashed locks and NOTICE inventory

- On Python 3.12.16, write `requirements.lock.txt` and `requirements-dev.lock.txt` with `pip-tools==7.6.2`, `pip-compile --generate-hashes`. Commit `package-lock.json` for Node 24.22.2, `@playwright/test==1.65.0`, and `http-server==14.1.1`.
- Fill NOTICE with every lockfile distribution (Python and npm) plus pinned dev tools and GitHub Action pins, each with version and a license taken from the distribution license file, not a blank classifier. Pillow remains a matplotlib transitive; do not import it.
- `tool/notice_check.py` parses the lockfiles and fails on a missing entry, a wrong version, or a blank license.

**Accept:** `pip install --require-hashes -r requirements-dev.lock.txt` succeeds on Python 3.12.16. `npm ci` succeeds. `python tool/notice_check.py` exits 0.

## 3. Seeded generator and kinematics

- Implement `generate("standard"|"clean", seed)` with PCG64, the locked scalar `normal` draw order, integer-microsecond stamps, the 100 Hz arc recurrence, and all eight injections from PLAN.md. Write CSV, JSONL (`NaN` tokens for gyro dropouts), and `ground_truth.json` (including F3 `held_gz`).
- No `time.time` or `time.time_ns`. Reject a nonempty `--out` directory.

**Accept:** `test_kinematic_checkpoints` (1e-12 at t = 8, 16, 20, 36, 48 and weave yaw at 50). `test_fault_injections`. `test_generate_bit_identical` in the same environment. `test_no_wall_clock`.

## 4. Parsers

- Implement `parse_csv_dir` and `parse_jsonl` to the same `RunLog`. Round-trip with NaNs equal. Seq must increase per stream; stamps need not be monotonic.

**Accept:** `test_csv_jsonl_roundtrip`. One test per parse code in PLAN.md, including `invalid_timestamp` for NaN/`t`, CLI exit 2, and no successful `score.json`.

## 5. Detectors F1–F7

- Implement the locked rules for `imu_bias`, `gyro_dropout`, `stuck_sensor`, `timestamp_gap`, `timestamp_jump`, `actuator_sat`, and `pose_jump`. Flag `t_host` from `seq`. Windowed flags use the right-edge host anchor.

**Accept:** `test_standard_precision_recall` (exactly 8 TP, 0 FP, 0 FN once F8 is also in). After this task, F1–F7 `test_latency_*` must already match `200000, 0, 300000, 400000, 0, 200000, 0` µs. `test_timestamp_disambiguation`. `test_clean_zero_flags` once F8 is quiet too.

## 6. Detector F8 and scoring

- Implement `clock_drift` exactly as in the revised PLAN.md: two-point interval rates, time-based smoother that does not bridge F2 NaNs, host-time windows `[t0, t1)`, grid search, **unidentifiable** if `|δ| = 1.0` or fewer than 10 pairs, **no** `midpoint >= 48` onset gate, first identifiable `|δ| >= 0.08` flags at the window end. `t_host = 55.00`, stream stamp at seq 5500 is `55.14`.
- Implement event-attribution scoring, `latency_us` by integer subtraction, `fta score --gate` (standard must be 8/0/0; clean/empty truth fails if any flag exists).

**Accept:** `test_latency_clock_drift` equals `7000000`. Clean max identifiable `|δ| < 0.08` and zero flags. All eight `test_disable_*` produce a FN.

## 7. Report, CLI, and sample site

- Jinja2 templates for `report.html` / `report.md`. Title `Field telemetry analyzer (synthetic data only)`. Banner `These are not real field logs.` Six matplotlib Agg PNGs, `flags.csv`, `index.html`. `fta` subcommands as in PLAN.md.

**Accept:** `test_report_artifacts` (files, title, banner, CSV header). Do not hash PNG bytes as a required gate.

## 8. Mutants, SPDX, and scope guards

- `tool/mutants.sh` applies M1–M8 as specified, requires the named node to be collected and to fail its assertion, restores bytes, rechecks the baseline.
- `tool/spdx_check.py` and `test_scope_guards` as in PLAN.md (including the allow-list for the forbidden word “invented”). `test_license_bytes`.

**Accept:** `tool/mutants.sh` exits 0 on the unmodified tree after killing all eight targets. SPDX and NOTICE checks exit 0.

## 9. CI and Pages workflow

- `ci.yml` jobs `lint`, `test`, `mutants`, `report`, `e2e` on ubuntu-24.04, Python 3.12.16, Node 24.22.2, Actions pinned by the SHAs in PLAN.md. No `continue-on-error`, no placeholder jobs.
- `e2e`: Playwright Chromium with `deviceScaleFactor: 1`, screenshot `scale: "css"`, `fullPage: false`, 1280×720, title and banner. Commit a local `docs/demo.png` of those dimensions; CI must not auto-commit it.
- `pages.yml` as in PLAN.md: `workflow_run` after green `ci` on `main`, download `pages-site` by run id, upload `github-pages`, smoke curl with at most 12 retries.

**Accept:** `test_scope_guards` finds the Pages guards. CI is green on the pushed branch (a completed run, not merely started).

## 10. Honesty pass

- README, report, and Pages strings match PLAN.md. Wording is “original implementation, inspired by.” No ML metrics, no live MQTT/Timescale/Grafana, no battery or actuator-power map, no real-field-log claim, no certification claim, no private-repo name required in the public README.

**Accept:** Criteria 1, 15, 16, and 18 in PLAN.md.
