# field-telemetry-analyzer

**Synthetic data only. These are not real field logs.**

An offline analyzer for IMU, pose, and actuator logs. It parses CSV or a ROS-bag-like JSONL file, plots the streams, raises simple explainable anomaly flags, scores those flags against injected ground truth, and writes a run report (HTML, Markdown, and a flags CSV).

This is an **original implementation, inspired by** well-known residual, windowed-statistic, and change-detection methods (see [REFERENCES.md](REFERENCES.md)). It is a portfolio demo, not production field-test software, not a certified FDIR system, and not anyone else's tooling.

## What this is not

- Not real robot, customer, or lab-field logs. Every fixture is generated in-repo by a seeded simulator with documented, injected faults.
- Not a live telemetry dashboard. It does not use MQTT, a time-series database, or Grafana.
- Not a battery or actuator-power map.
- Not a ROS / MCAP bag evaluation bench, and not an ML detector. There are no learned metrics.

## Faults the demo injects (ground truth)

On the `standard` scenario, seed `20261110`, a 60 s planar run, the generator injects eight faults of known time and magnitude: an IMU accel bias step, a gyro dropout (NaN), a stuck gyro, a pose timestamp gap, a backward timestamp jump, an actuator saturation, a pose jump, and IMU clock drift. Detectors are deterministic windowed statistics, residuals, and gap checks. They are scored against that sidecar ground truth. Precision and recall here mean a documented event-attribution count, not an ML metric.

A `clean` scenario uses the same trajectory and the same noise draws with no injections and must produce zero flags.

## Quick start (after the implementation is in the tree)

```bash
# Python 3.12.16 recommended (CI pin)
pip install --require-hashes -r requirements-dev.lock.txt
pip install -e .

fta generate --scenario standard --seed 20261110 --out /tmp/fta-standard
fta detect  --log /tmp/fta-standard --out /tmp/fta-standard-out
fta score   --log /tmp/fta-standard --truth /tmp/fta-standard/ground_truth.json \
            --flags /tmp/fta-standard-out/flags.csv --out /tmp/fta-standard-out/score.json --gate
fta report  --log /tmp/fta-standard --flags /tmp/fta-standard-out/flags.csv \
            --score /tmp/fta-standard-out/score.json --out /tmp/fta-standard-out --truth /tmp/fta-standard/ground_truth.json
```

A sample report, always labelled synthetic data, is published on GitHub Pages after green CI on `main`.

## Honest limits

- The IMU bias detector is evaluated only on 0.20 s block edges. A step that splits a block unfavorably can be missed; the demo fixture is aligned on an edge on purpose.
- The stuck-gyro detector looks for an exact digital freeze (`max == min`) plus motion, not a soft, noisy stall.
- Clock-drift lag is a coarse 1-D grid on a 60 s file with an exaggerated scale error `ρ = 0.02`. It is an offline windowed estimate, not a Kalman clock model, and not `t - seq * dt`.
- Kinematics are piecewise and planar. Velocity steps do not include impulsive accelerations.
- Plot PNG bytes can change with the renderer; tests hash flags and `score.json`, not images.

## License

Apache-2.0. Copyright 2026 Arpan Bom. See [LICENSE](LICENSE). A NOTICE file with dependency versions, licenses, and a pointer to [REFERENCES.md](REFERENCES.md) will be completed during implementation.
