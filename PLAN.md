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

**Phase 0 — Data (day 1–2).** ✦ Handle the IO-VNBD gotchas up front: column names carry a leading space (`skipinitialspace=True`); files are **latin-1**, not UTF-8; `GPS SATELLITES IN RANGE` is a string like `"27 / 28"`; the accelerator-pedal header is wrong (it's % activation); the synchronised folder is misspelled `Synchronised V abd S datasets`; CSVs are **Git LFS** (use `media.githubusercontent.com/media/...`). Smartphone data is 10 Hz sampling with a **1 Hz GPS update** — GPS rows repeat in blocks of ~10 and are not independent fixes. Run a deliberately naive double-integration baseline to document the drift floor.

✦ **Constraint to document now:** the WhONet benchmark **cannot be reproduced smartphone-only** — its splits are `V-` (ECU, England-only), and `V-St6`, `V-St7`, `V-S3a` (three of nine long-outage sequences) have no smartphone counterpart. **Define and publish your own S-side split.** All evaluation uses synthetic masking; the dataset's real dropouts have no ground truth and exist only as exclusions.

**Phase 1 — MVP (day 2–5).** CNN+GRU front end → nonholonomic InEKF → learned Q/R → blackout/blend FSM → ✦ chi-square innovation gate (cheap, no new sensor, closes a real gap).

**Phase 2 — Differentiators, ✦ reordered by verified value-per-hour:**
1. `L_cent` centripetal loss — highest value, lowest risk
2. GNSS-loss cause attribution — **bench-test AGC availability first**; fall back to C/N₀-only
3. Motion Bank + Gated Head (Tanh + Softplus — the paper's own best config, copy verbatim) + continuous scheduling
4. Heading-only gated map coupling
5. Scalar conformal inflation (~30 lines)
6. Rule-based context classifier (~1 day)
7. NavIC visibility panel
8. Ackermann curvature/friction bounds

**Phase 3 — Moonshot.** GNSS-supervised TTA (BN-affine only, replay buffer, hard revert on loss degradation). Speed-MoE with exogenous routing. **Mamba only if justified by the sweep below.**

✦ **Run before spending any Mamba effort:** sweep GRU context length at 1 / 5 / 10 / 20 s. Mamba's own Theorem 1 shows selection reduces exactly to a gated RNN at N=1 — there is no categorical gap over a GRU at T=200. If accuracy saturates at 2–4 s, cut Mamba from the plan.

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

Planning revision 2 complete, 2026-09-05. Research complete across nine tracks. Demo UI built ([demo/gnss-demo.html](demo/gnss-demo.html)). No estimator implementation started yet.
