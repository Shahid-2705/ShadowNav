# ShadowNav

**Smart India Hackathon 2026 — Problem Statement SIH26168 (ISRO)**

A smartphone-only (accelerometer + gyroscope, no external speed sensor) vehicle dead-reckoning system that holds position through GNSS blackouts — tunnels, multi-level parking, urban canyons — and blends back cleanly on GPS re-acquisition. The name refers to **GPS shadow**, the standard term for zones where satellite signal is blocked or degraded.

## The problem

Every commercial GNSS-denied dead-reckoning system (Baidu VDR, Amap's tunnel mode) is gated behind a vendor SDK, a hardware exclusive, or assumes a car's wheel-tick/CAN bus. India has no sovereign equivalent, no product targets the two-wheelers that make up ~75% of India's fleet, and NavIC currently has only 3 operational satellites — below the 4 needed for a fix. ShadowNav corrects IMU drift/bias, detects outage entry and re-acquisition, and dead-reckons through the gap using only sensors already in every phone.

## Repo layout

- **[PLAN.md](PLAN.md)** — the buildable project plan: positioning, full architecture with data contracts, phased build order, validation targets, risk register. Start here.
- **[plans/](plans/)** — architectural decision records ([ADR-001](plans/adr/ADR-001-lead-with-evaluation-rigour.md), [ADR-002](plans/adr/ADR-002-osm-heading-then-gated-speed-cut-rendering.md), [ADR-003](plans/adr/ADR-003-publish-fair-baselines-and-ps-target.md)), [winnability strategy plan](plans/winnability-plan.md), and [3D MVP blueprint](plans/shadownav-3d-mvp-web-deck.md).
- **[research/SIH26168-dead-reckoning-research.md](research/SIH26168-dead-reckoning-research.md)** — technical dossier: paper deep-reads (DMDVDR/AVNet, GNIO, FDIO, WiCHINS, PiDR), dataset survey, competitor landscape, cross-domain technique transfer.
- **[research/SIH26168-open-track-findings.md](research/SIH26168-open-track-findings.md)** — verification pass on nine proposed features, with buildable/not-buildable verdicts.
- **[research/SIH26168-external-review-response.md](research/SIH26168-external-review-response.md)** — response to an external 7.5/10 review that evaluated *pedestrian* DR by mistake.
- **[research/SIH-winning-decks-analysis.md](research/SIH-winning-decks-analysis.md)** — structure and evidence standards of past winning decks.
- **[research/SIH26168-adversarial-validation.md](research/SIH26168-adversarial-validation.md)** — evaluator-style audit of the whole submission.
- **[python/](python/)** — data pipeline, 5-state kinematic estimator, fair baselines (freeze, constant velocity, gyro heading), confidence gate, and evaluation harness. Start at [python/README.md](python/README.md).
- **[android/](android/)** — the live app. Sensor capture at 401 Hz, foreground service, SpeedNet ONNX bindings, and `shadownav-core` (pure-Kotlin module proved numerically identical to Python to 1e-9 by golden vectors). 2.2 MB release APK, minSdk 29. Start at [android/README.md](android/README.md).
- **[frontend/](frontend/)** — static React 19 + Three.js Web MVP replaying real recorded outages with interactive 3D signal orb visualization. Start at [frontend/README.md](frontend/README.md).
- **[demo/](demo/)** — single-file WebGL presentation demo (`gnss-demo.html`) simulating the GNSS-blackout → dead-reckoning → re-acquisition cycle for live pitching.
- **[shared/](shared/)** — the Python↔Android contract: SpeedNet PyTorch (`speednet.pt`) and ONNX (`speednet.onnx`) checkpoints, conformal factors (`conformal.json`), and usage rules.
- **[eval/](eval/)** — published sequence split (`eval/splits/shadownav_s_split.yaml`) and reproducible benchmark results (`eval/results/*.json`).

## Status

| Phase | State |
|---|---|
| Research + plan | complete |
| Response to external review | complete |
| **Phase 0** — data pipeline, split, drift floor | **complete** |
| **Phase 1** — filter core | **complete** |
| **Phase 1** — CNN+GRU learned speed front end | **trained, calibrated ($\sigma$-scale 3.27), ONNX exported, gated** |
| **Phase 2** — differentiators | **baselines (CV, freeze, gyro), OSM map heading constraint, confidence gate built** |
| **Phase E** — Android app | **builds, parity-proved (1e-9); 401 Hz capture & foreground service built; outdoor drive pending** |
| Phase 3 / submission pack | audit complete, templates and script blueprints ready |

## Where it stands, measured

79 sessions, 991 scored synthetic outages, one seed (`20260905`), one published split — `eval/results/` (scored under the corrected protocol where the evaluation fix is strictly unaided):

| Horizon | Naive strapdown floor | Freeze last fix | Constant velocity (no IMU) | ShadowNav Kinematic MVP | Gain over floor |
|---|---|---|---|---|---|
| 10 s | 310.0 m | 222.0 m | **181.7 m** | 194.3 m | 1.6× |
| 30 s | 1,724.5 m | 435.8 m | **345.5 m** | 377.5 m | 4.6× |
| 60 s | 6,856.1 m | 754.0 m | **611.8 m** | 657.8 m | 10.4× |
| 120 s | 26,688.0 m | 1,153.2 m | **979.3 m** | 1,086.1 m | 24.6× |
| 180 s | 63,408.1 m | 1,576.5 m | **1,325.8 m** | 1,480.0 m | 42.8× |

**250 tests pass** (1 test cleanly skipped when real hardware trip logs are absent), 0 failures. Every number above reproduces from a committed seed.

### Honest baseline findings (ADR-003)

- **The classical filter does not beat a straight line on 10 Hz / 9 s-GPS data:** Constant Velocity (extrapolating last GNSS velocity with zero IMU integration) achieves 182 m at 10 s and 1,326 m at 180 s, matching or edging out the filter (194 m / 1,480 m). In paired comparisons, the Kinematic MVP wins 49% (10 s), 36% (30 s), 34% (60 s), 29% (120 s), and 27% (180 s) of outages against Constant Velocity.
- **Why this happens:** In IO-VNBD, GPS fixes update only every ~9 s and the IMU logs at 10 Hz. The speed held into an outage is up to 9 s stale, road vibration cannot be observed at 10 Hz, and gyro heading integration slowly accumulates drift on mostly straight routes.
- **The on-device hypothesis:** On the physical moto g64 5G, `SensorCapture` measures **401 Hz** accelerometer/gyroscope rates. At 400 Hz, vibration and centripetal signatures are un-aliased, which is the decisive regime under which the inertial filter and SpeedNet are designed to operate.

### Calibrated confidence (no false certainty)

The filter's raw 90% covariance ellipses contain only **14%** of true positions on held-out routes (overconfident by 6–7×). A scalar conformal inflation fitted on the validation fold brings test containment to **96%** (nominal 90% target).
- Reported as *empirically calibrated coverage on held-out routes*, never guaranteed (trajectory errors are not exchangeable).
- Calibrated 90% ring radius: median **848 m** (10 s), **1.5 km** (30 s), **3.8 km** (60 s), **9.2 km** (120 s), and **13.7 km** (180 s).

### The learned speed front end & confidence gating

- **Architecture:** `models/speednet.py` — 128,373 parameters (0.52 MB fp32, ~0.13 MB INT8), DeepOdo/DeepOri convolutions + GRU + GNIO Motion Bank and sigmoid gate.
- **Calibration:** Val-fitted $\sigma$-scale is **3.27**, correcting Gaussian NLL under-dispersion.
- **The bias challenge:** On test routes, the raw network carries a +1.08 m/s driver-shift bias that flips sign on validation (-0.28 m/s), improving mid-horizons (9–13% at 30–120 s) but hurting 180 s (+18.8%).
- **Confidence Gate (`models/gate.py`):** Wraps SpeedNet in a rule-based gate with innovation bounds, rate limits, and a $\sigma$-threshold (`gate=1.5 m/s`), beating both the control and ungated SpeedNet at 10 s (121.0 m) and 180 s (859.7 m).
- **Edge Deployment:** Exported to ONNX (`shared/speednet.onnx`) and integrated into Android via ONNX Runtime Mobile (`SpeedNetOnnx.kt`).

### Four dataset findings

Auditing all 72 S-side IO-VNBD files surfaced four defects documented in [python/README.md](python/README.md): GPS updates every ~9 s rather than 1 Hz (only 14,067 real fixes across 1.07M rows), Excel date corruption of the satellite column in 12 of 72 files, concatenated recording sessions, and duplicate-timestamp rows. Each is repaired invertibly with dedicated regression tests.
