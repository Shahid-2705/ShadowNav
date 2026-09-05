# SIH26168 — Complete Project Plan

**Revision 2 (2026-09-05)** — updated after the open-track verification pass. Changes from revision 1 are marked ✦.

Companion documents:
- [research/SIH26168-dead-reckoning-research.md](research/SIH26168-dead-reckoning-research.md) — baseline dossier (papers, competitors, market, geopolitics)
- [research/SIH26168-open-track-findings.md](research/SIH26168-open-track-findings.md) — verification pass on nine features/tracks, with buildable verdicts. **Read before claiming anything is novel.**

---

## 1. Positioning

**What we're building:** a smartphone-only (accelerometer + gyroscope, no external speed sensor) vehicle dead-reckoning system that holds position through GNSS blackouts and blends back cleanly.

**Why this version wins:**
- The algorithm problem is *not* unsolved — China's Baidu ("VDR" SDK) and Amap (600+ tunnels since 2023) ship it at national scale. But **Baidu's VDR requires their Navigation SDK plus an advanced permission you must apply for**, and **Amap's premium lane-level tunnel mode is exclusive to Huawei Pura 80 hardware**. Neither is a general, open capability.
- **India has no sovereign equivalent.** Mappls, despite OEM and ISRO ties, has no public feature in this space.
- **Nobody targets India's actual vehicle mix** — two-wheelers are ~75% of the fleet; every commercial DR product assumes a car's wheel-tick/CAN architecture.
- ✦ **The patent lane is genuinely open.** Every verified in-force patent in phone-in-vehicle DR (STMicro, Huawei, TDK InvenSense, Baidu, Harman, TomTom) is deterministic/Kalman-based with **no ML**. The closest learned claim (Alma US20220228866A1 — a deep NN localizing a vehicle from IMU without GNSS) is **abandoned**; Qualcomm's neural-navigation patent expired in 2020. India's landscape is empty of relevant filings.
- **NavIC's operational crisis** (3 satellites, below the 4 needed for a fix) makes a software-side resilience story strategically live right now.

**Pitch framing:** *"China solved this for cars, behind an SDK gate and a hardware exclusive. Nobody has solved it for the vehicles most Indians actually ride — at the moment India's own satellite system needs a software-side answer."*

✦ **What NOT to claim.** The verification pass killed four novelty claims. Do not say: "we estimate sensor bias and mounting alignment online" (AVNet already does), "tightly-coupled map constraints are novel" (Fouque 2008), "context-adaptive switching is novel" (Gao & Groves), or "statistically guaranteed confidence" (exchangeability fails on trajectories). Each has a narrower defensible form — see §3.

✦ **FTO note for a commercialised version:** the real design-around is **STMicro US11199410B2**, covering phone-in-arbitrary-orientation misalignment and explicitly naming tunnels. Their claim is tied to *explicit axis determination* — so **learn** the misalignment rather than computing it via SVD, and you step outside it.

---

## 2. Core Architecture

### 2.1 Pipeline

```
TRIP-WIDE ✦ — opportunistic calibration during turns and speed changes
      (NOT a fixed pre-blackout window: parameters are only observable
       under motion excitation, and a straight constant-speed approach
       to a tunnel is close to the degenerate case)
                                 │
IMU (accel + gyro, 200 Hz)       │
  → gravity-align, device → vehicle frame
  → on-manifold preintegration (Forster/GTSAM-style) between updates
  → CNN+GRU front end (DeepOdo/DeepOri architecture)
      → forward-velocity + attitude-change pseudo-measurements
  → Motion Bank (GNIO) — 64 prototypes × 512-dim, MHA query
      → re-weighted by speed regime
  → Gated Prediction Head (GNIO) — Softplus(magnitude) ⊙ Tanh(gate)
      → ✦ gate strength continuously scheduled by confidence,
         not a per-window binary decision
  → ✦ Speed-MoE Router — routes on EXOGENOUS signals only
      [log-PSD bands, gyro energy, |a| stats, last-GNSS speed + age];
      convex soft mixing, ~2 s dwell hysteresis; detach() any path
      where the speed estimate could close the loop
  → Nonholonomic InEKF, 21-state SE₂(3)
      ↕ learned adaptive Q / R noise adapter
      ✦ + centripetal-consistency loss term (see 2.3)
  → ✦ GNSS DEGRADATION HANDLER (replaces the simple outage FSM)
      ├─ cause attribution: C/N₀ trend + AGC *sign* (event-level API 33)
      ├─ context classification: rule-based tree, 3-4 states
      ├─ blackout path: FSM → DEAD_RECKONING, fiducial re-anchor on
      │  the last known-good fix
      └─ ✦ degraded-but-present path: chi-square innovation gate +
         C/N₀ measurement de-weighting (urban canyon — GNSS is never
         "lost" there, it lies)
  → ✦ heading-only gated map constraint (never lateral)
  → ✦ conformal-inflated covariance → calibrated confidence output
  → Position / heading, no visible jump on re-acquisition
```

### 2.2 Component table

| # | Component | Source | Priority |
|---|---|---|---|
| 1 | Gravity alignment + on-manifold preintegration | Forster et al. / GTSAM | Stretch |
| 2 | CNN+GRU front end | DeepOdo/DeepOri (verified from code) | **MVP** |
| 3 | Nonholonomic InEKF, 21-state | AI-IMU-DR (MIT) + AVNet | **MVP** |
| 4 | Learned adaptive Q/R | AVNet (verified from code) | **MVP** |
| 5 | Blackout/blend FSM + fiducial re-anchor | Engineering; FSM itself not novel | **MVP** |
| 6 | ✦ Chi-square innovation gate + C/N₀ de-weighting | GNSS literature | **MVP** ✦ |
| 7 | ✦ Centripetal-consistency loss `L_cent` | Derived; PiDR precedent | **Phase 2, first** ✦ |
| 8 | ✦ GNSS-loss cause attribution (AGC sign) | J911, Spens et al. | Phase 2 ✦ |
| 9 | Motion Bank + Gated Head | GNIO | Phase 2 |
| 10 | Speed-conditioned bank re-weighting | New | Phase 2 |
| 11 | ✦ Continuous confidence-scheduled gating | Marine INS damping-loop analogy | Phase 2 ✦ |
| 12 | ✦ Heading-only gated map constraint | Fouque 2008 (cite it) | Phase 2 ✦ |
| 13 | ✦ Scalar conformal covariance inflation | Barber et al.; ~30 lines | Phase 2 ✦ |
| 14 | ✦ Rule-based context classifier | Gao & Groves (cite it) | Phase 2 ✦ |
| 15 | ✦ NavIC visibility/health panel | Instrumentation only | Phase 2 ✦ |
| 16 | Ackermann curvature/friction bounds | GNIO fix #3 | Phase 2 |
| 17 | ✦ GNSS-supervised test-time adaptation (BN-affine only) | TENT, UL-VIO | Phase 3 ✦ |
| 18 | ✦ Speed-MoE router | GNIO fix #2, circularity resolved | Phase 3 ✦ |
| 19 | ✦ Mamba backbone | **Gated on a context-length sweep** | Deferred ✦ |

### 2.3 ✦ The centripetal-consistency term — highest value per line

```
L_cent = ‖a_y^measured − v̂_forward · ω_z^gyro‖²
```

Couples predicted forward speed to two **directly measured** quantities. Rearranged, `v = a_y / ω_z` — so **every turn during a blackout becomes an independent speed observation** that doesn't depend on integrating accelerometer noise. Basis of production yaw-rate virtual sensors. **No wheelbase parameter appears.**

Supporting terms:
```
L_nhc  = ‖v̂_lat‖² + ‖v̂_up‖²                   wheelbase-free
L_curv = max(0, |ω_z| − v̂·κ_max)²              κ_max ≈ 0.28 m⁻¹ covers all cars
         friction bound |v̂·ω_z| ≤ μg (~0.8g)   parameter-free
```
Gate all Ackermann terms off above ~0.5 g lateral acceleration, where tire slip breaks the bicycle model.

### 2.4 Tech stack

✦ **3D rendering engine (added 2026-09-05, blueprint Step 1).** Raw `com.google.android.filament:filament-android` (1.75.1, confirmed live on Maven Central this session — Filament moves fast, re-check before bumping), not SceneView: SceneView's current 4.x line is Compose-native and would pull in the entire Compose runtime, which this app has deliberately never used (see `Ui.kt`'s file comment on why there's no design system to inherit beyond `demo/gnss-demo.html`). Raw Filament is a plain `SurfaceView`/`TextureView` API with no Compose dependency. **Measured cost:** adding the dependency alone (before any rendering code) moved the release APK from 2,226,384 bytes to 5,393,603 bytes (+3,167,219 bytes, ~2.4x) with the ABI filter restricted to `arm64-v8a` only (`android/app/build.gradle.kts`) — with both `armeabi-v7a` + `arm64-v8a` it was +5,553,955 bytes (7,780,339 total) instead, so dropping 32-bit support saved back about 2.4 MB. `arm64`-only is deliberate: minSdk 29 (Android 10+, 2019+) devices are overwhelmingly 64-bit-capable and Google has required 64-bit support for all new Play Store submissions since August 2019, so a 32-bit-only handset at this minSdk is vanishingly rare. Revisit if a real 32-bit-only target device turns up, or if an Android App Bundle (per-device splitting) is chosen over a sideloaded universal APK.

**On-device capability probe, first real run (moto g64 5G, `arm64-v8a`, API 35 — confirmed via `adb shell getprop`, the same phone the 401 Hz measurement in commit `439bca7` came from).** The off-screen EGL/GLES benchmark (`GpuBenchmark.kt`, an unthrottled pbuffer render, not a displayed-frame measurement — see the FIX-8 note in `plans/shadownav-3d-mvp-web-deck.md`) measured **33.7 ms** for a fixed synthetic 400-iteration-per-pixel trig workload on a 256×256 surface, which puts this device below the current (guessed, unvalidated) `REDUCED_3D` threshold of 20 ms and resolves to `RenderTier.Canvas2D`. **This is not yet a real finding about whether Filament rendering will run acceptably on this device** — the synthetic benchmark's absolute number isn't calibrated against any actual Filament scene, only internally consistent for ranking devices against each other, and there is currently exactly one data point. Treat `RenderTierThresholds` as provisional until Step 2 builds a real orb scene and Step 5 correlates its actual measured frame time against this probe's number on the same device — only then does "abandon 3D on this device" become a decision backed by a real measurement rather than an arbitrary synthetic shader's threshold.
- **Mobile:** Kotlin/Android. Raw `GnssMeasurement` access is the only path to AGC and per-constellation data.
- **On-device inference:** TFLite/ONNX, INT8. (A competitor's benchmark showed quantization *improved* their ATE, 1.61 → 1.42 m — worth replicating, not just a size win.)
- **Training:** Python + PyTorch.
- **Filter core:** implement from `mbrossar/ai-imu-dr` (MIT). Do **not** vendor the unlicensed DragonEmperorG repos.
- **Map matching:** `leuvenmapmatching` to prototype (only one exposing lattice probabilities); **Valhalla Meili** for on-device (C++, tiled, built for offline). OSRM is out — server-only, and its confidence returns 0 on correct matches.

### 2.5 ✦ Android API facts (verified, not assumed)

| Need | API | Status |
|---|---|---|
| Per-satellite C/N₀ | `GnssStatus.getCn0DbHz()` | API 24, universally populated |
| AGC level | `GnssMeasurementsEvent.getGnssAutomaticGainControls()` | **API 33** — the older `GnssMeasurement.getAutomaticGainControlLevelDb()` is deprecated as of API 34 |
| NavIC satellites | `GnssStatus.CONSTELLATION_IRNSS` = 7 | **API 29** — exists. An earlier note in this project claiming otherwise was wrong |
| Per-satellite fix contribution | `GnssStatus.usedInFix(i)` | Available |
| Permissions | `ACCESS_FINE_LOCATION` only | No Developer-Options toggle needed |

> ⚠ **Open risk:** AGC is reported *as a field on a GnssMeasurement*, and per Google's javadoc it is not reported when a signal is too weak to acquire — **i.e. it may go silent inside a tunnel, the primary target scenario.** Whether the event-level API-33 path still delivers AGC with zero tracked satellites is undocumented. **Bench-test this on target hardware before committing to the feature.** Mandatory C/N₀-only fallback.

---

## 3. Differentiators — what to actually claim

Each claim below is the *narrowed, defensible* version that survived verification.

1. ✦ **GNSS-supervised test-time adaptation across heterogeneous phones.** Not "online bias/mounting estimation" — AVNet does that already. What AVNet does *not* do: use GNSS at runtime, or update learned weights at deployment. Its own stated limitation is a rigidly-fixed phone and no cross-device generalization. Cite Wahlström/Skog/Händel (FUSION 2015) for alignment; note OSS-Transformer (IEEE T-VT 2024) as the nearest prior art.
2. ✦ **Centripetal-consistency speed observability.** Wheelbase-free, measurement-grounded, and directly targets the hardest case (constant-speed tunnel cruising).
3. ✦ **GNSS-loss cause attribution.** PS-named requirement. Frame as blockage-vs-interference attribution — blockage is the common case DR must handle anyway; jamming is the rare consequential tail. **India's documented interference is aviation, not roads** (~465 reports Nov 2023–Feb 2025 near Amritsar/Jammu; DGCA 10-minute reporting mandate). Do not claim Indian highways are widely jammed.
4. ✦ **Handling the urban canyon as a distinct problem.** GNSS is never *lost* there — it lies (>50 m NLOS errors while reporting a fix; 92.5% of code outliers are NLOS). A pure outage FSM never fires. Innovation gating + C/N₀ de-weighting closes a real gap against a PS-named scenario.
5. ✦ **Honest calibrated confidence.** Raw EKF covariance is documented as *overconfident* in dead-reckoning (NEES > 1). A scalar conformal inflation fitted on held-out routes fixes that. Say **"empirically calibrated coverage — 90% containment on held-out routes."** Never "guaranteed." Pre-empt the judge by naming exchangeability yourself.
6. ✦ **NavIC visibility panel.** Enumerate NavIC satellites, C/N₀, and which entered the fix — live. Technically honest and uniquely ISRO-relevant. **Do not claim a positioning improvement**: only 1–3 NavIC satellites are currently usable by a phone (legacy IRNSS is L5+S-band; NVS-01 is the only operational L1 satellite) against the 4 needed for a fix.
7. **Two-wheeler / gig-fleet targeting.** Every paper and competitor trains on cars. Two-wheelers have a different vibration signature and no CAN bus. 260M+ vehicles, zero purpose-built products.
8. **On-device, no cloud.** Sovereignty narrative, and genuinely necessary — there's no network in a tunnel.

---

## 4. Build Plan

**Phase 0 — Data (day 1–2).** ✦ Handle the IO-VNBD gotchas up front: column names carry a leading space (`skipinitialspace=True`); files are **latin-1**, not UTF-8; `GPS SATELLITES IN RANGE` is a string like `"27 / 28"`; the accelerator-pedal header is wrong (it's % activation); the synchronised folder is misspelled `Synchronised V abd S datasets`; CSVs are **Git LFS** (use `media.githubusercontent.com/media/...`). ~~Smartphone data is 10 Hz sampling with a **1 Hz GPS update** — GPS rows repeat in blocks of ~10~~ — **corrected 2026-09-05, measured not assumed:** IMU is 10.00 Hz but the **GPS fix period is a median of 9.0 s** (89.4 rows per fix; only 3 of 79 sessions look like 1 Hz), i.e. ~27 m of travel between consecutive fixes and just **14,212 real position observations in the whole dataset**. Score only at rows carrying a real fix; report actual elapsed time and the truth gap. Three further undocumented defects — Excel-date corruption of the satellite column (12 files, biased toward exactly the low-satellite rows we care about), concatenated recording sessions (5 files), duplicate-timestamp rows (7 files) — are repaired in `python/shadownav/data/repair.py`. See the corrected Track H.

**Phase 0 status: COMPLETE (2026-09-05).** Drift floor documented at `eval/results/baseline_naive.json` — naive unaided strapdown, 79 sessions, 991 scored outages:

| Horizon | CRSE median | CRSE p90 | CTE median | Drift median |
|---|---|---|---|---|
| 10 s | 310 m | 639 m | 113 m | 229% |
| 30 s | 1,725 m | 3,690 m | 906 m | 444% |
| 60 s | 6,856 m | 13,729 m | 3,996 m | 918% |
| 120 s | 26,688 m | 52,997 m | 14,201 m | 1,844% |
| 180 s | 63,408 m | 112,594 m | 39,385 m | 2,553% |

Consistent across train/val/test folds. Comparable to the ">1000% error" a competitor documents for the same construction (dossier §10, tannaakshat447). Every later claim is measured against this.

✦ **Constraint to document now:** the WhONet benchmark **cannot be reproduced smartphone-only** — its splits are `V-` (ECU, England-only), and `V-St6`, `V-St7`, `V-S3a` (three of nine long-outage sequences) have no smartphone counterpart. **Define and publish your own S-side split.** All evaluation uses synthetic masking; the dataset's real dropouts have no ground truth and exist only as exclusions.

**Phase 1 — MVP (day 2–5).** ~~CNN+GRU front end → nonholonomic InEKF → learned Q/R → blackout/blend FSM → chi-square innovation gate.~~

**Phase 1 status: filter core COMPLETE (2026-09-05), learned front end NOT started.** Results at `eval/results/kinematic.json` — 79 sessions, 991 outages, same split, seed and windows as the floor:

| Horizon | Naive floor | MVP | Gain | Drift | NEES |
|---|---|---|---|---|---|
| 10 s | 310 m | **189 m** | 1.6× | 108% | 132 |
| 30 s | 1,725 m | **372 m** | 4.6× | 100% | 132 |
| 60 s | 6,856 m | **658 m** | 10.4× | 88% | 120 |
| 120 s | 26,688 m | **1,056 m** | 25.3× | 84% | 96 |
| 180 s | 63,408 m | **1,463 m** | 43.4× | 77% | 89 |

✦ **Architecture change forced by measurement.** The 21-state strapdown InEKF is built and its Jacobians are verified against finite differences (`python/tests/test_ekf.py`), but it **cannot be used on IO-VNBD**: the smartphone side logs at 10 Hz, so the accelerometer is aliased, and with GNSS fixes 9 s apart there are ~90 free double-integration steps between corrections. Run on this data it reached 5×10⁴ m/s. The deployed MVP is a **5-state 2D kinematic filter** — gyro-integrated heading plus held speed — which never double-integrates acceleration. Keep the strapdown for the Android app, where the IMU runs at 100–200 Hz.

✦ **Two planned features measurably *hurt* on this data and are defaulted off.** Ablation over 152 outages: enabling `L_cent` and accelerometer-driven speed raised CRSE at every horizon (180 s: 924 m → 1,530 m) and worsened median NEES from 28–74 to 103–548. Both read the accelerometer's *horizontal* channels, which need the device-to-car alignment and are aliased at 10 Hz. **`L_cent` is not refuted — it is untestable on 10 Hz logs.** Re-run the ablation on 100–200 Hz Android data before drawing any conclusion about the technique. This independently reproduces Agastya's ablation (§10): unconstrained correction is worse than the classical baseline; only the gated version wins.

✦ **Device-to-car alignment is a prerequisite, not a refinement.** Applying the nonholonomic constraint in the phone's frame rather than the car's produced 1,312 m at a 10 s horizon — four times *worse* than the unaided strapdown. Alignment is observable in ~84% of runs; where it is not (a straight, constant-speed approach — the degenerate case at §6.2) the constraint is disabled rather than applied wrongly.

**Remaining Phase 1 gap — the dominant error term.** Drift is still 77–108%, far from the AVNet 0.64% reference and worse than PathPulse's claimed 10%. The residual is **speed staleness**: speed is held from the last fix, which can be 9 s before the outage even starts, then held through it. Closing this is exactly the job of the CNN+GRU forward-speed front end, which is specified and wired (`SpeedEstimator` protocol, `pipeline_kinematic.run(speed_estimator=...)`) but **not yet trained**. Highest-value remaining item.

**Phase 2 — Differentiators, ✦ reordered by verified value-per-hour.** Status as of 2026-09-05:

| # | Item | Status | Outcome |
|---|---|---|---|
| 1 | `L_cent` centripetal loss | **built, defaulted OFF** | Implemented as a *measurement* (`update_centripetal`), not a loss — every turn observes speed via `a_lat = −v·ψ̇`. Measurably **hurts** on IO-VNBD: 180 s CRSE 924 → 1,530 m. It reads the accelerometer's horizontal channels, which need the alignment and are aliased at 10 Hz. **Not refuted — untestable on this data.** Re-run on 100–200 Hz Android data. |
| 2 | GNSS-loss cause attribution | **blocked** | IO-VNBD's S-side carries no C/N₀ or AGC column at all, so neither the primary nor the fallback path can be validated offline. Needs the Android bench test (§7 Q2) before any code is worth writing. |
| 3 | Motion Bank + Gated Head | **built** | GNIO's bank (32×96, MHA, residual fusion) and gated head, inside the CNN+GRU speed net. ✦ **Deliberate departure:** GNIO's Tanh gate is validated for a *signed displacement vector*; forward speed is a non-negative scalar where a [−1,1] gate can only reach zero by cancelling the magnitude branch. Uses a [0,1] sigmoid, keeping the soft-ZUPT property. Both selectable and ablated. |
| 4 | Heading-only gated map coupling | not started | Needs OSM/Valhalla. Unchanged from plan. |
| 5 | Scalar conformal inflation | **built** | The biggest honesty win in the project. Raw 90% ellipses contain **17%** of errors (λ = 15–22, NEES 18–153); calibrated, 97%. Fitted on val, measured on test. |
| 6 | Rule-based context classifier | **blocked** | Same reason as #2 — no C/N₀ in the S-side data. |
| 7 | NavIC visibility panel | not started | Android-only by nature. |
| 8 | Ackermann curvature/friction bounds | **built, marginal** | 180 s: 945 → 871 m (−7.8%); 10 s: 124 → 126 m (+1.4%). Kept on for the hard case. ✦ **Bug found:** the friction bound was dead code — the 0.5 g slip gate (4.9 m/s²) is tighter than the bound itself (μg = 7.85 m/s²), so gating a slip limit by a slip test filtered out every violation before it could fire. Friction now applies unconditionally; only curvature keeps the slip gate. |

✦ **Two Phase-2 items are blocked on a dataset limitation, not on effort.** IO-VNBD's smartphone side has no carrier-to-noise or AGC column, so cause attribution (#2) and the context classifier (#6) cannot be built or falsified offline at all. This strengthens rather than weakens the case for §7 open question 2 — the AGC bench test is now the gate for two features, not one.

**Phase 3 — Moonshot.** GNSS-supervised TTA (BN-affine only, replay buffer, hard revert on loss degradation). Speed-MoE with exogenous routing. **Mamba only if justified by the sweep below.**

✦ **Run before spending any Mamba effort:** sweep GRU context length at 1 / 5 / 10 / 20 s. Mamba's own Theorem 1 shows selection reduces exactly to a gated RNN at N=1 — there is no categorical gap over a GRU at T=200. If accuracy saturates at 2–4 s, cut Mamba from the plan.

**✦ Phase E — Android (added; status 2026-09-05).** Built and compiling. Two Gradle modules: a pure-Kotlin/JVM estimator with no Android dependency, and the app. Release APK **2.2 MB**, minSdk **29** (set by `CONSTELLATION_IRNSS`, not by habit).

The estimator is **proved numerically identical to the Python implementation** — nine golden cases exported from Python, replayed in JUnit, agreement to 1e-9, covering geodesy, propagation, every measurement type, the gate escape, the Ackermann bounds, the blend spring, alignment and the invariant features. §2.4's requirement that the Kotlin path be verified against Python before any on-device number is trusted is therefore satisfied.

The app measures the **achieved IMU rate** rather than assuming 200 Hz, and shows it as a headline diagnostic — every offline negative result depended on that variable. AGC is reported in three honest states (unavailable below API 33 / supported-but-silent / a value), which is what makes the §3.3 claim survivable. The confidence ring is the **calibrated** 90% radius, never the raw covariance.

Nothing was enabled on device merely because more data is available: forward-acceleration speed and `L_cent` stay off until their ablations are re-run at the rate the phone actually delivers.

**Not done:** no on-device latency, battery or thermal measurement; no drive-log export; the learned speed head is not wired in (it is off in the offline pipeline too); and the 21-state strapdown is still unused even though the phone's higher rate is exactly the condition under which it should work — that is the first experiment to run.

✦ **Blueprint Steps 1-2 (added 2026-09-05): Filament status orb, real-device verified.** A capability-gated (`RenderTier`) Filament orb now sits next to the status chip, both driven by one shared `uiState()` function so they can't disagree about what's currently true — the exact hazard (asserting a GNSS lock with zero satellites before the first fix) that the original chip-only code already guarded against. Verified end-to-end on the connected moto g64 5G, not just compiled: a screenshot bug (the sphere overflowed the camera frustum and rendered as a flat filled square) was caught and fixed by actually looking at the device, not by code review alone; three of the six states (`ACQUIRING`, `GNSS AIDED`, `SIMULATED BLACKOUT`) were confirmed by screenshot to render the orb and chip in identical colour and label via the UI-layer debug harness (long-press the chip), with the remaining three covered by the same code path plus unit tests. Deliberately deferred: the demo's full per-shard fracture animation (this pass has a colour cross-fade + gentle rotation/pulse instead) — a real, working rendering pipeline came first, matching the physics later is Phase-4-adjacent polish, not silently dropped scope.

**A second measured cost, caught the same way as the first.** The orb's material is built from a runtime-compiled `MaterialBuilder` source rather than a `.filamesh`/`.filamat` build-time asset (there is still no `matc`/`filament-tools` toolchain anywhere in this project — that needs a locally-built Filament C++ project). Linking `filamat-android` to do that compile at runtime was measured, not assumed, and cost **8.9 MB** of release APK size (5.39 MB → 14.3 MB) for a single ~80 KB material — `filamat-android` bundles the *full* shader cross-compiler toolchain (glslang/SPIR-V), sized for build-time tooling, not for permanent inclusion in a shipped app. Fix: ran it once on-device, extracted the compiled ~80 KB binary via `adb pull`, committed it as `android/app/src/main/assets/materials/orb.filamat`, and removed `filamat-android` from the app's dependencies entirely — `OrbMaterial.load()` now just reads the asset. Net cost of the orb feature: **+114 KB** (5.39 MB → 5.51 MB), not +8.9 MB. Re-verified on-device after the swap: identical render.

The device's own capability probe (Step 1) measures `Canvas2D` for this phone against the current provisional thresholds, meaning the orb does not appear in the shipped, non-overridden build on this hardware yet — everything above was verified via a manual `RenderTier` override written directly into the app's `SharedPreferences`, not the device's natural resolution. Recalibrating `RenderTierThresholds` against this now-real orb (rather than the synthetic EGL benchmark alone) is the next open item before Step 1's on-device gate can be trusted.

✦ **Blueprint Step 3 (added 2026-09-06): real-world map route scene, a third measured cost.** The route scene is built as MapLibre Native (`org.maplibre.gl:android-sdk` 13.6.0) style layers over a bundled, offline OpenMapTiles-schema vector tileset — never a second Filament scene composited with the map (two independent GL engines don't cheaply composite on Android; the review that caught this, FIX-2, is why the orb and the map route are architecturally separate views). The tileset was generated for real with Planetiler from a live OSM extract (Monaco — a small, well-known placeholder region chosen deliberately so the whole pipeline could be built and verified now; swapping in the actual demo route later is a one-file change, see the Step 0 note above) and is bundled as `assets/maps/monaco.mbtiles` (458,752 bytes), copied to internal storage once and opened via `mbtiles://file://` (the pattern MapLibre's own maintainers confirm working — direct in-APK-asset access has open reliability reports). `AndroidManifest.xml` still declares **zero network permissions**: MapLibre's own AAR manifest unconditionally merges in `INTERNET`/`ACCESS_NETWORK_STATE`/`ACCESS_WIFI_STATE`/`ACCESS_COARSE_LOCATION` (for features this app never uses — network tile fetching, MapLibre's built-in location layer), and all four are explicitly stripped via `tools:node="remove"` so the shipped permission set stays honest to what the app actually does and the "on-device, no cloud" pitch (§3.8) holds.

**The size cost, measured precisely, not estimated:** `libmaplibre.so` alone is **12,828,528 bytes (12.24 MB)** in the arm64-v8a release build — bigger than Filament's entire footprint (3.15 MB) plus both bundled assets (0.46 MB tiles + 0.08 MB material) combined. Release APK total: **19,514,341 bytes (18.6 MB)**, up from 5,507,081 bytes after Step 2 — a real, large jump, consistent with (not a surprise reversal of) the user's explicit choice to prioritise a full 3D engine and a real map look over the project's original low-end-hardware size budget. Recorded here rather than smoothed over, matching how the Step 1 Filament cost and the Step 2 `filamat-android` cost were both handled.

**A side effect worth flagging:** getting MapLibre 13.6.0 to compile required bumping the project's Kotlin version from 2.0.21 to 2.4.0 (MapLibre's AAR carries Kotlin-metadata requiring 2.2.0+). The estimator parity suite (`ParityTest`, 12 cases) and `StationaryDetectorTest` (9 cases) were re-run unmodified after the bump and both still pass bit-for-bit — the Kotlin toolchain change did not touch `shadownav-core`'s numerical behaviour.

**Ring math, preserved exactly.** The confidence ring is drawn as a real geographic polygon (`GeoCircle`, a small equirectangular approximation, plain-JUnit tested) at `sigmaM * conformalLambda * 2.146` metres — never a MapLibre `circle-radius`, which is fixed in screen pixels and would not shrink/grow correctly when the map is zoomed. `TrackView.conformalLambda`'s existing public-property coupling to `MainActivity`'s "90% RADIUS" metric is untouched; `MapRouteView` is simply handed the same loaded value.

**Two known, accepted trade-offs of a real map**, not yet exercised on real driving data: (1) the project's honestly-reported 77-108% drift will read as "driving through buildings" on a real basemap rather than "an abstract estimate," a change in legibility, not in the underlying number; (2) `PLAN.md` risk #3's multi-storey-car-park scenario has no OSM road network at all and will render as blank ground under the trail there — expected, not a bug. Both need to be in the pitch deck's back pocket (blueprint Step 11).

**Not yet done:** on-device airplane-mode verification that the bundled tileset actually renders with zero network (the core promise of this step) — pending device availability at time of writing; the dynamic trail/ring/vehicle layers were exercised via a debug-harness synthetic path (extending Step 2's long-press harness) rather than a live outdoor GPS fix, since this indoor test environment never acquires one. `INTERNET` remaining absent from the manifest is independently verified, so the app is structurally incapable of a network request regardless.

✦ **Visual polish pass (2026-09-06): bloom on the orb, real 3D building extrusion on the map.** Two "make it look more advanced" upgrades, both using capability already in place rather than new dependencies:
- The orb's material now emits colour boosted past the tone mapper's normal range (`emissiveBoost = 2.5`) with `View.BloomOptions.enabled = true`, so it reads as genuinely glowing rather than just brightly coloured -- a flat-colour pulse can't produce that regardless of how bright the colour is.
- The map's `buildings` layer changed from a flat `fill` to a real `fill-extrusion`, using Planetiler's own `render_height`/`render_min_height` fields (present in the tileset's metadata already, not new data), with the camera tilted 55° -- extrusions are visually identical to flat fills from a straight-down camera, since you only ever see roofs either way.
- Also redesigned the launcher icon (`ic_launcher_foreground/background/monochrome.xml`): the existing concept (a heading chevron piercing a broken confidence ring, same colour language as the app) is unchanged, but it now has a radial background vignette, layered glow strokes, and a gradient-filled chevron instead of flat colour, so it reads as lit rather than printed. Confirmed rendering correctly via the system App Info screen.
- **Honesty note:** the bloom and building-extrusion changes are confirmed crash-free and style-valid (style loads, all layers parse) on the connected device, but not yet visually confirmed by screenshot -- the device has been in active personal use during this work, and screenshot attempts twice caught personal content (a home screen, then a WhatsApp contact list), the second of which was sensitive enough that automated on-device screenshotting was stopped entirely for the remainder of this session. Visual confirmation of these two changes specifically is an open item, not a claimed-working result.

**Phase 4 — Validation & pitch.** IO-VNBD replay with synthetic masking on your documented split. Demo the outage → reacquisition transition with no visible jump — the PS's literal grading criterion.

---

## 5. Validation targets

| Source | Metric | Value | Note |
|---|---|---|---|
| AVNet/DMDVDR | Drift, 578 m / 55 s real tunnel | **0.64%** | Phone IMU only, no map, no GNSS — the fair comparison |
| AVNet/DMDVDR | Parking lot | 0.4% | |
| ✦ WhONet | CTE / CRSE @ 120 s | 1.78 m / 2.62 m | **Uses wheel-speed sensors** — upper reference, not like-for-like |
| ✦ WhONet | CTE / CRSE @ 180 s | 0.49 m / 3.93 m | 8.62 m over 5.6 km |
| Agastya (competitor) | ATE, gated policy | 1.42–1.64 m | Their ungated ML was *worse* than classical (2.76 m) |
| PathPulse (competitor) | Mean drift | 10.0% | |

✦ Report CTE (cross-track) and CRSE (cumulative resultant) at 10/30/60/120/180 s to match the field's convention.

---

## 6. Risk register

1. ✦ **AGC may be unavailable in tunnels** — the feature's primary scenario. Bench-test before building. Fallback: C/N₀-only.
2. ✦ **Degenerate excitation** — a straight, constant-speed tunnel approach is the worst window for calibration. Calibrate opportunistically during turns instead.
3. ✦ **Wrong map-match corrupts the filter** in a tightly-coupled design. Heading-only, multi-gate, hard-disable on zero candidates. Note: **no road network exists inside multi-storey car parks** (OSM terminates service roads at the entrance) — one of the PS's own scenarios.
4. **Small-dataset overfitting** — AVNet's own set is 11 sequences from one parking lot.
5. **License risk** — DragonEmperorG repos are unlicensed. Build on `ai-imu-dr` (MIT); IO-VNBD is CC BY 4.0 via its Data in Brief version.
6. **Two-wheeler data scarcity** — the most differentiated angle has the least data.
7. ✦ **Overclaiming.** Four novelty claims already failed verification. Shanghai Jiao Tong's own lab reports IMU fusion in real <4-satellite conditions is still "insufficient for long-term reliability." Pitch the well-scoped slice.

---

## 7. ✦ Open questions blocking decisions

1. **Verbatim PS text** — two conflicting accounts of the named scenarios. Gates the context classifier's target set.
2. **Does event-level AGC survive a tunnel?** Bench test. Decides whether feature #3 works at all.
3. **Does SIH26169 exist** as a companion PS? Reported, unverified.
4. **Which demo phone?** Settles AGC availability, barometer presence, and NavIC support simultaneously.
5. **Barometer garage-ramp discriminator** — plausible, consistent with published barometer use, but no paper validates that specific discriminator.

---

## Status

Planning revision 2 complete, 2026-09-05. Research complete across nine tracks. Demo UI built ([demo/gnss-demo.html](demo/gnss-demo.html)).

**Phase 0 (data) complete, 2026-09-05** — see [python/README.md](python/README.md). Loader with regression tests for every documented and newly-found dataset hazard, published S-side split, synthetic-masking harness, and the naive drift floor. Four dataset findings not in the research dossiers were fed back into Track H. Estimator implementation (Phase 1) is next.
