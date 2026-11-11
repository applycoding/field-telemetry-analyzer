# References

Idea-only credits for **field-telemetry-analyzer**. This is an **original implementation, inspired by** the public documents and projects below. Do not copy source from them. Outbound license for this demo is **Apache-2.0**.

Checked 2026-11-10. Licenses were taken from the project's license file or `package.xml` when GitHub's SPDX API was empty or `NOASSERTION`.

This demo must stay distinct from existing applycoding work (list checked 2026-11-10 with `gh repo list applycoding --limit 200`; `applycoding/field-telemetry-analyzer` did not exist at planning time):

| Repo | What it already is | How this demo differs |
| --- | --- | --- |
| [applycoding/robot-fleet-mqtt-telemetry](https://github.com/applycoding/robot-fleet-mqtt-telemetry) | Live fleet pipeline: MQTT, TimescaleDB, webhook rules, Grafana | Offline file-in / report-out analyzer. No broker, database, or live stream. |
| Private actuator-power / battery-pitch log work | Not used and not a source | This demo does not build a power or battery map. Do not copy that work. |
| applycoding/rosbag-eval-bench (planning) | MCAP bag metric regression | No MCAP, no planner or detection mAP, no baseline-regression bench. |
| [applycoding/teleop-console-demo](https://github.com/applycoding/teleop-console-demo) | Browser teleop record/replay | Offline IMU, pose, and actuator anomaly report, not a console. |
| [applycoding/flutter-robot-operator](https://github.com/applycoding/flutter-robot-operator), ekf-gnss-localization, sim-gimbal-stabilizer | Operator UI, estimator, gimbal controller | Different problem. Do not reuse their code. |

## Selected references

### 1. ROS `sensor_msgs/Imu` field naming

- URL: https://github.com/ros2/common_interfaces
- Path: `sensor_msgs/msg/Imu.msg`
- License: **Apache License 2.0** (`sensor_msgs/package.xml` on the `rolling` branch, checked 2026-11-10)
- Borrow: the idea of reporting body-frame linear acceleration and angular velocity with an explicit timestamp. This repo does not depend on ROS and does not vendor the message package. The log field names `ax, ay, az, gx, gy, gz` are an original, reduced schema.

### 2. REP 103, standard units and frames

- URL: https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst
- Rendered: https://www.ros.org/reps/rep-0103.html
- License: the source repository did not publish a machine-readable SPDX identifier in this check; cite the public informational REP only, do not copy the document into this tree.
- Borrow: the idea of SI units and a body frame with x forward, y left, z up. This is not a ROS integration.

### 3. matplotlib (plotting tool, also a runtime dependency)

- URL: https://github.com/matplotlib/matplotlib
- License: matplotlib license agreement (versions 1.3.0 and later), file `LICENSE/LICENSE` on `main`, checked 2026-11-10
- Docs: https://matplotlib.org/stable/users/project/license.html (HTTP 200 on 2026-11-10)
- Borrow: ordinary use of the public plotting API for the run-report figures. Do not vendor matplotlib sources.

### 4. Windowed change detection and residual checks (literature)

- Michèle Basseville and Igor V. Nikiforov, *Detection of Abrupt Changes: Theory and Application*, Prentice-Hall, 1993, ISBN 0-13-126780-9. Author PDF (informational, idea only): https://people.irisa.fr/Michele.Basseville/kniga/ (do not copy text or code from the book).
- Borrow: the general idea of comparing a trailing window statistic to a threshold, and of scoring detections against known injection times. The block-mean `imu_bias` rule in this demo is an original, deliberately simple implementation, not a CUSUM library and not a reproduction of the book's algorithms.

### 5. Time-delay estimation by a lag grid

- The classical idea of estimating a delay by maximizing a similarity measure over a one-dimensional lag, common in signal processing (cross-correlation / squared-error delay estimation). No specific library is vendored.
- Borrow: the idea of a discrete lag search between a gyro trace and a pose-derived yaw rate. The window lengths, quality gate (`|δ| = 1.0` is unidentifiable), and `|δ| >= 0.08` flag rule are original to this demo.

### 6. `ros/diagnostics` (reporting idea only)

- URL: https://github.com/ros/diagnostics
- License: **BSD-3-Clause** (root `LICENSE` and `diagnostic_aggregator/package.xml` on the `ros2` branch, checked 2026-11-10)
- Borrow: the general idea of a human-readable diagnostic report. Do not copy aggregator or updater sources, and do not depend on the package.

## Not used, and not to be added

- Production FDIR or certification standards as a claim (ISO 26262, flight qualification).
- ML libraries or learned detectors.
- MQTT, TimescaleDB, Grafana, ROS runtime, MCAP, or bag-evaluation harnesses.
- imu_tools, robot_localization, foxglove, PlotJuggler, DiagnosticAggregator sources, or any private log-analysis repository.
