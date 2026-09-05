# ShadowNav

**Smart India Hackathon 2026 — Problem Statement SIH26168 (ISRO)**

A smartphone-only (accelerometer + gyroscope, no external speed sensor) vehicle dead-reckoning system that holds position through GNSS blackouts — tunnels, multi-level parking, urban canyons — and blends back cleanly on GPS re-acquisition. The name refers to **GPS shadow**, the standard term for zones where satellite signal is blocked or degraded.

## The problem

Every commercial GNSS-denied dead-reckoning system (Baidu VDR, Amap's tunnel mode) is gated behind a vendor SDK, a hardware exclusive, or assumes a car's wheel-tick/CAN bus. India has no sovereign equivalent, no product targets the two-wheelers that make up ~75% of India's fleet, and NavIC currently has only 3 operational satellites — below the 4 needed for a fix. ShadowNav corrects IMU drift/bias, detects outage entry and re-acquisition, and dead-reckons through the gap using only sensors already in every phone.

## Repo layout

- **[PLAN.md](PLAN.md)** — the buildable project plan: positioning, full architecture with data contracts, phased build order, validation targets, risk register. Start here.
- **[research/SIH26168-dead-reckoning-research.md](research/SIH26168-dead-reckoning-research.md)** — technical dossier: paper deep-reads (DMDVDR/AVNet, GNIO, FDIO, WiCHINS, PiDR), dataset survey, competitor landscape, cross-domain technique transfer.
- **[research/SIH26168-open-track-findings.md](research/SIH26168-open-track-findings.md)** — verification pass on nine proposed features, with buildable/not-buildable verdicts. Read before claiming anything is novel.
- **[research/SIH26168-external-review-response.md](research/SIH26168-external-review-response.md)** — response to an external 7.5/10 review that evaluated *pedestrian* DR by mistake. Carries the corrected weighted scorecard (4.1/10 today → 6.2/10 at MVP), the PDR→vehicle translation table, and the low-end-device hardware decision.
- **[demo/](demo/)** — single-file WebGL presentation demo (`gnss-demo.html`) simulating the GNSS-blackout → dead-reckoning → re-acquisition cycle for live pitching.
- **[python/](python/)** — data pipeline, estimator, evaluation harness, learned speed net. Start at [python/README.md](python/README.md).
- **[android/](android/)** — the live app. The estimator is a pure-Kotlin module proved numerically identical to Python by a golden-vector parity suite. 2.2 MB release APK, minSdk 29.
- **[shared/](shared/)** — the Python↔Android contract: model checkpoint, conformal factors, and the rules for using them.

## Status — 2026-09-05

| Phase | State |
|---|---|
| Research + plan | complete |
| Response to external review | complete |
| **Phase 0** — data pipeline, split, drift floor | **complete** |
| **Phase 1** — filter core | **complete** |
| **Phase 1** — CNN+GRU learned speed front end | **trained, opt-in** |
| **Phase 2** — differentiators | **4 of 8 built, 2 blocked on missing data** |
| **Phase E** — Android app | **builds, parity-proved; no on-device measurement yet** |
| Phase 3 / submission pack | not started |

**Where it stands, measured.** 79 sessions, 991 scored synthetic outages, one
seed, one published split — `eval/results/`:

| Horizon | Naive strapdown floor | ShadowNav MVP | Gain |
|---|---|---|---|
| 10 s | 310 m | **180 m** | 1.7× |
| 30 s | 1,725 m | **368 m** | 4.7× |
| 60 s | 6,856 m | **640 m** | 10.7× |
| 120 s | 26,688 m | **1,071 m** | 24.9× |
| 180 s | 63,408 m | **1,474 m** | 43.0× |

161 tests pass. Every number above reproduces from a committed seed.

**Confidence is calibrated, and that mattered.** The filter's own 90% ellipses
contain **17%** of errors on held-out routes — overconfident by 15–22×. A
scalar conformal inflation fitted on val brings that to 97% on test. Reported
as *empirically calibrated coverage*, never as guaranteed: trajectory errors
are not exchangeable.

**The learned speed front end is trained and opt-in.** 128k parameters, 0.13 MB
INT8, ~19 ms projected on a low-end core against a 30 ms budget. It improves
position 9–13% at 30–120 s and makes it 19% worse at 180 s, because it carries
a +1.08 m/s bias that is a driver-shift artefact rather than a model property —
val and test biases have opposite signs, so it cannot be corrected from
held-out data. Off by default until it is confidence-gated.

**Not yet good enough, and we say so.** Drift is 77–108% of distance travelled,
against the 0.64% AVNet field reference and a competitor's claimed 10%. The
dominant residual is speed staleness — speed is held from a GNSS fix that can
be 9 s old before the outage even starts. The learned front end that closes it
is specified and wired but untrained.

**Four dataset findings** not present in any prior source are recorded in
[python/README.md](python/README.md): GPS updates every ~9 s rather than 1 Hz,
Excel date corruption of the satellite column in 12 of 72 files (biased toward
exactly the low-satellite rows this project cares about), concatenated
recording sessions, and duplicate-timestamp rows.
