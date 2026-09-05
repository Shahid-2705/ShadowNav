# SIH26168 — Dead Reckoning Research Dossier

**Problem statement:** SIH26168, ISRO — "AI-ML based Intelligent Dead Reckoning system for seamless navigation."
Build a smartphone-only (accelerometer + gyroscope, no external speed data) module that keeps a vehicle's position tracked through GPS blackouts (tunnels, multi-level parking, urban canyons), corrects sensor drift/bias/vibration noise, detects outage entry and re-acquisition, and blends cleanly back to GPS. Validation target, **paraphrased** (NOT verbatim — see correction note): replay an IO-VNBD sequence with GPS artificially cut through a tunnel-length section, showing the AI dead-reckoning track holding close to ground truth.
**Correction note (2026-09-05):** earlier revisions presented the line above inside quotation marks as if it were verbatim ISRO text. It is not — it originated from a third-party summary site (sih-buddy.vercel.app), not the official problem statement.

**Verbatim PS fragments now available** (supplied by a collaborator who has the official text; still PARTIAL — the full PS has not been seen in this session):
- On causes of signal loss: *"GNSS signals are inherently weak and vulnerable to structural blockage (urban canyons, dense foliage, tunnels, deep valleys) and unintentional electromagnetic interferences from variety of sources such as jamming."*
- A requirement bullet titled *"Advanced Map-Matching & Kinematic Constraints"*, calling for OSM as *"a framework... that binds the calculated position to known road networks."*
- A stated **10 Hz update-rate requirement** (referenced by the collaborator; the surrounding verbatim sentence has not been seen).

**⚠ UNRESOLVED DISCREPANCY — do not build scenario-classification logic until settled.** Two accounts of the PS's named scenarios conflict:
- The verbatim quote above names: **urban canyons, dense foliage, tunnels, deep valleys**.
- A separate collaborator message names "four distinct blackout scenarios": **tunnel, multi-level parking, dense forested highway, urban canyon**.
These lists differ on two of four entries (multi-level parking and dense forested highway appear in one; dense foliage and deep valleys in the other). Possible benign explanation: the PS names blockage *causes* in its background section and test *scenarios* in its expected-outcomes section separately, and the two lists come from different parts. But that is a guess. The full PS text is needed to resolve it. This matters directly: an outage-type context classifier must be trained on the scenario set the PS actually grades against, and "multi-level parking" (a GNSS-total-denial, low-speed, high-turn environment) versus "deep valleys" (partial-sky, high-speed) imply different designs.

Rendered version with tables/diagram: published Artifact **"Ded Reckoner"** — https://claude.ai/code/artifact/2a0af494-38e0-4434-8d1a-47c0f46cc0fd (ask the user for current status/link if it's moved; this file is the durable source of truth).

Researched 2026-09-04, in four passes. Pass 1: two source papers supplied by the user plus one found during research (§1), with background subagents covering the GitHub code ecosystem and the academic prior-art landscape (§2-§5). Pass 2: a live sweep of ~14 Indian SIH26168-tagged GitHub repos actively being built by other teams (§10). Pass 3: international prior art outside the Indian SIH ecosystem, and cross-domain technique transfer from SLAM, drone/UAV, marine INS, AR/VR, warehouse robotics, and gait analysis (§11-§12), plus a strategic finding on NavIC's live 2026 operational crisis (§12a). Pass 4: global technology/market landscape — NASA and space-agency precedent, China's ecosystem (BeiDou, Baidu/Amap, academia, state strategy), other major nations (Russia, EU, Japan, South Korea), and commercial market analysis (§13), synthesized into a gap analysis (§14) and future-tech roadmap (§15). Confidence is marked per claim — treat anything marked "medium" as directional, not exact, and re-verify numbers before quoting them in a submission.

---

## 0. Verdict

**Neither source paper solves SIH26168 alone.**

- **DMDVDR/AVNet** (2025) is a real, field-tested vehicle dead-reckoning system — a CNN+GRU velocity/attitude regressor bolted to a classical filter — but has no learned drift-suppression mechanism beyond that.
- **GNIO** (2026) has the sharpest drift-suppression mechanism in the literature (Motion Bank + Gated Head) — but its own authors tested it on vehicle datasets (KITTI, GEODE) and it **degraded significantly**. The paper's own §V names the cause (pedestrian ZUPT logic breaks at highway speed) and proposes three specific, unexecuted fixes. Nobody — including GNIO's authors — has built those fixes.

**Correction to keep in mind:** GNIO was *tried* on vehicles and documented failing — it is not an "untried idea." That's a *stronger* claim to make to a judge than "novel and untested," because you can point at the paper's own admission and name exactly what was fixed.

**Proposed synthesis** (full detail in §6 below): graft GNIO's Motion Bank + Gated Prediction Head onto a vehicle-native nonholonomic InEKF in the DMDVDR / AI-IMU-Dead-Reckoning lineage, close GNIO's three named gaps (Mamba backbone, speed-based Mixture-of-Experts, Ackermann kinematic constraint), and add the one thing neither paper touches at all: an outage-detection / blend-back state machine — because both papers benchmark against continuous GPS-denial, not real intermittent GPS, and re-acquisition handling is explicitly what the PS grades on.

---

## 1. The Source Papers

### 1.1 DMDVDR / AVNet — the proven vehicle system
**Confidence: high on headline numbers (cross-confirmed across two sources), medium on the detailed per-baseline table (proxy-extracted, Springer sat behind a cookie-wall).**

Qian et al., *"Avnet: learning attitude and velocity for vehicular dead reckoning using smartphone by adapting an invariant EKF,"* Satellite Navigation, Jun 2025. Wuhan University / Chongqing University.
Full author list (verified against Crossref metadata for DOI 10.1186/s43020-025-00168-7, 2026-09-05): Long Qian, Xinchuang Lin, Xiaoguang Niu, Qihai Huang, Leilei Li, Guangyi Guo, Zexin Wang, Ruizhi Chen.
**Correction note:** earlier revisions of this dossier cited this paper as "Wang et al." That was wrong — Zexin Wang is 7th of 8 authors, not first. The error came from cross-contamination with the separate 2023 DeepOdo paper (§2), whose author list genuinely does begin with Wang. Flagged by a collaborator, then independently confirmed via Crossref.
Springer: https://link.springer.com/article/10.1186/s43020-025-00168-7
Press release (headline numbers source): https://www.eurekalert.org/news-releases/1089377

**What it is:** DMDVDR (Data- and Model-Driven Vehicle Dead Reckoning) = three parts:
1. **AVNet** — CNN+GRU network turning raw IMU windows into pseudo-measurements of vehicle attitude and forward velocity.
2. A small adapter network that predicts process/measurement noise covariances **online** instead of using fixed values.
3. An **Invariant EKF (InEKF)** on SE₂(3), 21-state nonholonomic vehicle filter (nav rotation/velocity/position, gyro/accel biases, car-frame rotation/position).

**Architecture, verified directly from the authors' own public code** (`DragonEmperorG/QDeepOdo` — high confidence, this is real code, not a paper-text summary):
- Per-timestep CNN front end: `Conv1d(6→128, k=11) → Conv1d(128→256, k=9)`, ReLU + MaxPool after each.
- Velocity branch (DeepOdo): flatten → `FC(1536→1024→512→1)`.
- Attitude branch (DeepOri): same CNN front end → `FC(11008→1024→512) → GRUCell(512→512) →` final 3-output layer.
- This CNN+GRU pair is DeepOdo/DeepOri — the lineage AVNet is built from.

**InEKF + adapter, verified directly from `DragonEmperorG/QAIIMUDeadReckoning` code (high confidence):**
- 21-D state: nav rotation(3×3) + velocity(3) + position(3), gyro/accel biases(3+3), car-frame rotation(3×3) + position(3).
- SO(3) exponential-map propagation, gravity-compensated velocity integration, trapezoidal position integration.
- Measurement: forward car velocity (the AVNet pseudo-measurement).
- `NoiseCovarianceModel`: `Linear(1,6) + tanh` → **18×18 process-noise Q** (6 blocks: gyro noise, accel-bias noise ×2, gyro-bias noise, vehicle-rotation noise, vehicle-position noise).
- `AdaptiveParameterAdjustmentModel`: small dilated CNN (`Conv1d 6→32→32`, dropout 0.5) + `Linear(32,3)+tanh` → **3×3 measurement-noise R**.
- Both scaled as `base × 10^(β·tanh(·))`, β≈3 → ±3 orders of magnitude adaptive range. This functional form appeared identically in both the code and a separate paper-text extraction — cross-confirmed.

**Results (headline numbers, cross-confirmed via press release + reconstruction):**

| Result | Value |
|---|---|
| Parking-lot horizontal error | 0.4% of distance |
| General horizontal error | < 0.5% |
| Real tunnel: 578m, 55s GPS loss (Google Smartphone Decimeter Challenge, Pixel 5) | 0.64% drift |

**Dataset (medium confidence, proxy-extracted):** custom collection, Huawei Mate 30 phone (STMicro LSM6DSM IMU) vs. Novatel SPAN/ISA-100C reference (cm-level, 200Hz); 11 sequences (5 rectangular ~285m loops, 5 S-shaped, 1 reverse-parking), 5/10/15 km/h, one surface parking lot simulating underground conditions. Second dataset: 39 trajectories from GSDC 2023-2024 Pixel 5 collection for the tunnel test.

**Stated limitations (medium confidence):** phone mounting was fixed during data collection; dataset is small (11 sequences, one location); vertical error worse than horizontal due to flat-ground assumption; parking lot had a slight slope.

**Baseline comparison methods named in the paper:** AI-IMU (original 2D-velocity-constraint method), DeepOdo (AI-IMU + learned 3D velocity), DeepOri (AI-IMU + learned 3D attitude) — DMDVDR = both + dynamic filter adaptation. Exact per-baseline numeric table could not be verified directly (Springer cookie-wall) — treat any specific baseline percentages beyond the three headline figures above as approximate.

**Code (all repos, license: none/all-rights-reserved — see §4):**
- https://github.com/DragonEmperorG/QDeepOdo — AVNet's CNN+GRU (velocity + attitude nets)
- https://github.com/DragonEmperorG/QAIIMUDeadReckoning — InEKF + noise adapter
- https://github.com/DragonEmperorG/VDRDataCollector — Android data logger

Circumstantial evidence these are the paper authors' own repos: `VDRDataCollector`'s Java package is `cn.edu.whu.lmars` = Wuhan University LMARS lab, matching the paper's Wuhan University affiliation. Not explicitly confirmed by the repos' own text.

### 1.2 GNIO — the sharpest drift model, wrong domain
**Confidence: high — read directly from the paper's own PDF pages, tables read visually, not summarized.**

Feng, Yin, Chen, Qi, Chen (Sun Yat-sen University / HKU), *"GNIO: Gated Neural Inertial Odometry,"* arXiv:2603.15281, submitted 16 Mar 2026.
https://arxiv.org/abs/2603.15281

**Motion Bank:** learnable matrix `M ∈ ℝ^(m×D)`, m=64 prototypes (optimal, swept 16/32/64/128), D=512, of archetypal motion patterns (static, walking, running, turning). Current ResNet-18 feature `f_k` is the Multi-Head-Attention **query**; `M` serves as both keys and values:
```
Q = f_k·W_Q,  K = M·W_K,  V = M·W_V
c_k = Softmax( (f_k·W_Q)(M·W_K)^T / √d_k ) · (M·W_V)
h_k = f_k + c_k     (residual fusion)
```
Effectively: "which of the motions I've seen before does this window resemble" — differentiable long-range memory a sliding-window CNN otherwise lacks.

**Gated Prediction Head:** displacement split into magnitude and direction/confidence:
```
s̃_k = Softplus(W_s·h_k + b_s)     (magnitude, ≥0)
g_k  = Tanh(W_g·h_k + b_g)        (gate/direction, [-1,1])
d̂_k  = s̃_k ⊙ g_k                  (elementwise product = final displacement)
```
During stationarity the network drives `g_k → 0` — a soft, **differentiable** Zero-Velocity Update (classical ZUPT is a hard threshold).

**Loss:** `L = λ_MSE·L_MSE + λ_NLL·L_NLL` (displacement MSE + Gaussian NLL over a regressed log-variance uncertainty, same two-stage strategy as TLIO). Adam, batch 1024, linear warmup + cosine annealing LR (1e-6 → 1e-4 over 5 epochs, decaying to 1e-6 over 200 epochs total).

**Backbone:** 1D ResNet-18 modified for inertial signal, window N=100 samples @100Hz IMU (or N=200 @200Hz), stride S=N/10, gravity-aligned input rotation using current EKF orientation estimate. Fused via TLIO's Stochastic Cloning EKF.

**Results — Absolute Trajectory Error in metres, read directly off the paper's Table II (bold = best in column):**

| Method | OxIOD seen | OxIOD unseen | RIDI seen | RIDI unseen | RoNIN seen | RoNIN unseen | IDOL seen | IDOL unseen |
|---|---|---|---|---|---|---|---|---|
| TLIO | 2.67 | 2.54 | 1.58 | 1.49 | 5.95 | 7.10 | 5.89 | 5.34 |
| CTIN | 2.32 | 3.34 | 1.39 | 1.86 | 4.62 | 5.61 | 2.90 | 3.69 |
| iMoT | 1.86 | 0.90 | 1.68 | 1.49 | **3.78** | **5.31** | **2.22** | **3.00** |
| DeepILS | – | – | 1.56 | 1.48 | 4.80 | 6.80 | – | – |
| **GNIO** | **0.74** | **0.71** | **1.22** | **1.19** | 4.31 | 5.02 | 3.45 | 3.89 |

GNIO dominates OxIOD (60.21% better than runner-up iMoT) and RIDI (19.59% better than DeepILS on unseen). On RoNIN/IDOL the heavier Transformer (iMoT) still leads in the seen split, though GNIO closes the gap on unseen data — the paper frames this as Motion Bank generalizing better than iMoT's full-sequence attention.

**Compute (Table I) — this is the detail that matters for on-device deployment:**

| Architecture | Params (M) | GFLOPs |
|---|---|---|
| TLIO (ResNet-18+EKF) | 5.42 | 0.08 |
| DeepILS | 2.29 | 0.03 |
| **GNIO** | 4.90 | **0.08** |
| CTIN (Transformer) | 0.56 | 7.27 |
| iMoT (Transformer) | 14.49 | 7.79 |

GNIO gets within reach of Transformer-level accuracy at **~100× less compute** than the Transformer baselines — the difference between real-time on-device and needing a server.

**Ablation (Table III, TLIO dataset):**

| Configuration | RMSE (m) | Gain |
|---|---|---|
| Baseline (TLIO) | 2.40 | – |
| + Motion Bank only | 1.98 | 17.5% |
| + Gated Head only | 1.84 | 23.3% |
| **+ Both (full GNIO)** | **1.66** | **30.8%** |

**Best gate design (Table IV, already validated — copy this verbatim):** Tanh gating beats Sigmoid (2.00m vs 2.05m RMSE). Of magnitude-scale functions: **Softplus wins (1.84m)**, then PosELU (1.85m), Abs (1.92m), Exp (1.94m).

**Motion Bank size sweep (Fig. 2):** m=16→2.07m, m=32→2.01m, **m=64→1.98m (optimal)**, m=128→2.07m — both under- and over-provisioning hurt about equally.

**The critical passage — §V Limitations and Future Work (verbatim quote):**
> "While GNIO demonstrates robust performance on pedestrian datasets, its accuracy degrades significantly when applied to vehicle-based datasets such as KITTI and GEODE. The primary reason for this degradation lies in the physics of error propagation at high velocities... in automotive scenarios where speeds frequently exceed 10 m/s, the same relative error magnitude translates into massive absolute position drift... unlike pedestrian navigation, where frequent stops help reset drift via ZUPT, continuous high-speed driving lacks such constraints."

**Three unexecuted fixes named by the paper itself:**
1. **Long-Sequence Modeling** — replace the sliding-window backbone with a State Space Model (Mamba) to capture long-term acceleration dependencies (addresses observability during constant-speed cruising).
2. **Mixture of Experts** — dedicated low-speed / high-speed experts, gated by a dynamic router reading vibration signature.
3. **Kinematic Constraints** — bake non-holonomic / Ackermann-steering geometry into the loss.

None of the three have been built by anyone, GNIO's own authors included. **This is the gap the proposed architecture in §6 closes.**

Authors: Dapeng Feng, Yizhen Yin, Zhiqiang Chen, Yuhua Qi, Hongbo Chen. Sun Yat-sen University, Guangzhou / University of Hong Kong. No public code repository found for GNIO.

### 1.3 FDIO — proof that fix #1 already works elsewhere
**Confidence: medium — abstract and methodology read from paper text extraction, full results tables not independently re-verified.**

Zhang, Wu, Cao, Zheng, Yang, *"FDIO: Frequency Decomposed Inertial Odometry,"* arXiv:2511.15645v4, Nov 2025.
https://arxiv.org/abs/2511.15645

Splits raw IMU into frequency bands via a Laplacian pyramid; runs a **Mamba** state-space backbone over the long-range band and multi-scale convolution over the local-dynamics band. Pedestrian-only, no Motion Bank or gating. Compared against TLIO/RoNIN/IONet/RIDI baselines (exact numbers not independently confirmed).

**Why it matters here:** it's independent, contemporaneous (same ~6-month window) evidence that GNIO's own "future direction #1" — swap the backbone for Mamba — is a live, working idea elsewhere in the literature, not a speculative footnote. Materially de-risks building it as part of the proposed architecture.

---

## 2. Lineage Map

Two branches of the same family tree that mostly evolved without talking to each other.

**Pedestrian branch — drift-correction ideas:**
- 2018 — **IONet** (Chen et al., AAAI, arXiv:1802.02209) — first to replace analytic double-integration with an LSTM regressing per-window displacement. No confirmed public code found for the original.
- 2018 — **RIDI** (Yan, Shan, Furukawa, ECCV, arXiv:1712.09004) — regresses velocity, corrects raw acceleration to stay consistent with it. 10 subjects, 4 phone placements, ~150 min @200Hz, Tango/Phab2 Pro ground truth. Code (MIT): https://github.com/higerra/ridi_imu
- 2020 — **RoNIN** (Herath, Yan, Furukawa, ICRA, arXiv:1905.12853) — the benchmark: 100 subjects, 42.7 hrs, heading-agnostic velocity regression, ResNet/LSTM/TCN baselines. Site: https://ronin.cs.sfu.ca/ — Code (GPLv3, copyleft — mind this if reusing): https://github.com/Sachini/ronin
- 2020 — **TLIO** (Liu et al., Meta Reality Labs + UPenn, RA-L, arXiv:2007.01867) — tight EKF coupling: network predicts displacement AND its uncertainty, fed directly into the filter's measurement update. The baseline every later paper in this branch beats.
- 2025 — **CTIN / iMoT / DeepILS** — Transformer- and lightweight-edge variants; heavier accuracy ceiling, heavier compute (see Table I above).
- Nov 2025 — **FDIO** — frequency-decomposed + Mamba backbone.
- Mar 2026 — **GNIO** — Motion Bank + Gated Head. Tested on vehicles, degraded, named the fix. *(current frontier)*

**Vehicle branch — filter-fusion ideas:**
- 2020 — **AI-IMU Dead-Reckoning** (Brossard, Barrau, Bonnabel) — CNN-adapted InEKF enforcing nonholonomic (no lateral/vertical slip) vehicle motion, tested on KITTI. Code (MIT, 1,001★): https://github.com/mbrossar/ai-imu-dr — **the direct ancestor of DMDVDR's InEKF half.**
- 2021 — **VeTorch / "Glow in the Dark"** — TCN re-projecting phone-frame IMU into vehicle-frame regardless of mounting angle; explicitly tunnel-tested. Closest smartphone-only vehicle precursor to the PS's exact framing. https://www.researchgate.net/publication/349901602
- 2023 — **DeepOdo** (Wang, Weng, Qu, Ding, Chen, IEEE Trans. Instrumentation and Measurement, DOI 10.1109/TIM.2023.3240227, PolyU) — CNN-GRU vehicle velocity network fused with IMU+barometer via a classical filter. Reproduced in `QDeepOdo` above. Reported 73.14%/98.33% horizontal/vertical improvement over constraint-only baselines (per subagent finding, not independently re-verified).
- Jun 2025 — **DMDVDR / AVNet** — attitude+velocity CNN+GRU, learned-noise InEKF, field-validated on a real tunnel. *(current vehicle-branch frontier)*

**Other 2023-2026 vehicle-adjacent papers found (not deeply read, noted for follow-up):**
- "Learning Car Speed Using Inertial Sensors for Dead Reckoning Navigation" (2022), arXiv:2205.07883
- "An Inertial Sequence Learning Framework for Vehicle Speed Estimation via Smartphone IMU" (2025), arXiv:2505.18490
- "Deep Learning-Based Vehicle Speed Estimation Using Smartphone Sensors in GNSS-Denied Environment" (MDPI Applied Sciences, 2025), DOI 10.3390/app15168824
- "Tracking Large-scale Shared Bikes with Inertial Motion Learning in GNSS Blocked Environments" (2026), arXiv:2605.07412 (e-bike, same GNSS-blocked framing)
- "AbolDeepIO" — surfaced via Semantic Scholar only, **not independently verified**, flag as unconfirmed.

**Prior SIH solutions:** searched specifically for a prior Smart India Hackathon (any year) solution to a GPS-denied dead-reckoning problem statement. **None found publicly.** Only tangential hits (a non-SIH student tunnel-navigation project, generic unrelated `smart-india-hackathon`-tagged repos). Treat as "no known direct competition to check against," not proof none exists — SIH team repos are unevenly indexed; check sih.gov.in archives directly by PS ID/year if this matters later.

---

## 3. Datasets

| Dataset | Domain | Scale | GPS outage segments | Access |
|---|---|---|---|---|
| **IO-VNBD** (the PS's own validation target) | Vehicle + pedestrian | ~40hr/1,300km vehicle · ~58hr/4,400km phone; UK, Nigeria, France | None pre-labelled — PS expects synthetic GPS cuts, matching its own wording exactly | https://github.com/onyekpeu/IO-VNBD (public) |
| Google Smartphone Decimeter Challenge | Vehicle | 62+ drives, SF/LA | Urban canyon; the specific 578m/55s LAX tunnel segment DMDVDR used | https://www.kaggle.com/competitions/smartphone-decimeter-2023 (public, Kaggle) |
| comma2k19 | Vehicle | 33+ hr, CA highway | None confirmed | https://github.com/commaai/comma2k19 (public) |
| KITTI raw | Vehicle | Standard AV benchmark | Only ~1s interpolated OXTS dropouts | https://www.cvlibs.net/datasets/kitti/raw_data.php (public) |
| Boreas Road Trip (2026) | Vehicle | Multi-sensor, "challenging roads" | Unclear, not verified in depth | Appears public, arXiv:2602.16870 |
| OxIOD | Pedestrian | 158 seq, 42.5km/14.7hr | Indoor, N/A | http://deepio.cs.ox.ac.uk/ (public) |
| RIDI | Pedestrian | ~150min @200Hz, 10 subjects | N/A | https://yanhangpublic.github.io/ridi/ (public) |
| RoNIN | Pedestrian | 42.7hr, 100 subjects | N/A | Partial (~50% withheld for privacy) |

No India-specific or dedicated tunnel/GPS-outage driving dataset was found. **IO-VNBD stays the right primary choice** — it's exactly what the PS names — with GSDC's real 578m tunnel as a second, real-world (not synthetically-cut) sanity check, since DMDVDR already proved that segment is learnable to 0.64% drift.

---

## 4. Code Assets — what to actually build on

| Repo | What it is | License | Verdict |
|---|---|---|---|
| `DragonEmperorG/QDeepOdo` | DeepOdo/DeepOri CNN+GRU velocity & attitude nets (AVNet lineage, likely authors' own — Wuhan Univ. LMARS package match) | **None** (all-rights-reserved) | Read for architecture & hyperparameters. Don't vendor as-is. 7★, 2 forks, 13 commits. |
| `DragonEmperorG/QAIIMUDeadReckoning` | 21-state nonholonomic InEKF + learned noise adapter | **None** | Read for the adapter math only. README nearly empty (low doc confidence). 2★, 1 fork, 28 commits. |
| `DragonEmperorG/VDRDataCollector` | Android logger, 31-column CSV (schema below) | **None** | Reference for what to log if collecting own phone data. |
| **`mbrossar/ai-imu-dr`** | The CNN-adapted nonholonomic InEKF `QAIIMUDeadReckoning` descends from — vehicle-focused, KITTI-tested | **MIT, 1,001★** | **Build the filter core on this, not the unlicensed repo.** |
| `CathIAS/TLIO` | Tight EKF coupling reference | Other/NOASSERTION — check terms | Reference only. 405★. |
| `Sachini/ronin` | ResNet/LSTM/TCN velocity-regression baselines | **GPLv3** | Copyleft — fine to learn from, risky to vendor into a proprietary submission. 423★. |
| `higerra/ridi_imu` | Classic double-integration + ML bias correction, C++ | **MIT** | Safe to reuse patterns from. 236★. |
| `Adhithi02/dead_reckoning` | GPS+IMU+KF+ML correction, vehicle-focused | None | Small/unproven (6★) — worth skimming for structure only. |

**License note:** all three DragonEmperorG repos return `"license": null` via the GitHub API — no LICENSE file means default all-rights-reserved despite public visibility. GNIO and FDIO have **no public code repos at all**. Recommended honest path: implement the Motion Bank / Gated Head / noise-adapter math from the papers' own published equations (all reproduced in §1 above, all citable), rooting the InEKF core in `ai-imu-dr`'s MIT-licensed implementation rather than the unlicensed one.

**VDRDataCollector's full 31-column CSV schema** (0-indexed): 0=time; 1-3 accelerometer; 4-6 gyroscope; 7-10 game rotation vector (quaternion-like); 11-14 rotation vector (magnetic-corrected); 15-17 gyroscope uncalibrated; 18-20 orientation; 21-23 magnetic field; 24-26 gravity; 27-29 linear acceleration; 30 pressure. No sampling rate documented in README; a Chinese-language spec doc (`数据采集格式说明_20220315.docx`, dated 2022-03-15) exists in the repo but wasn't accessible during research.

---

## 5. Industrial Players

Why "smartphone-only, ML-corrected" is a real niche, not a compromise: no dedicated hardware-INS player competes in this exact lane.

| Player | Approach | Why it's not a competitor here |
|---|---|---|
| u-blox (NEO-M8U/M9V/M9L) | Hardware IMU + wheel-tick fusion, classical algorithms | Needs dedicated ADR/UDR silicon, not a bare smartphone |
| VectorNav, Trimble | Tactical-grade GNSS+INS fusion | High-cost hardware, not consumer-phone-class |
| Bosch Sensortec, STMicroelectronics | Automotive-grade IMU silicon | Component suppliers, not full navigation stacks |
| Inertial Labs | Named "Tunnel Guide" feature for GNSS-aided INS | Classical filter on dedicated hardware — same problem framing, worth name-dropping in a submission for context |

No ISRO-affiliated or Indian academic group (IISc, CDAC, IIT navigation labs) was found publicly working on smartphone-only vehicle dead reckoning specifically. IIT Tirupati's GNSS Technology Development Cell (IITTNiF) focuses on NavIC receiver hardware, not this. The entire literature reviewed above is UK/China/US-authored — this gap looks real, not a search miss.

---

## 6. Proposed Architecture

GNIO's drift-suppression core, transplanted into a vehicle-native nonholonomic filter, with its own three named gaps closed.

**Pipeline** (updated after §11-§12 research — changes marked ✦):
```
Trip start ✦ — UMBmark-style calibration maneuver (short drive/turn
      pattern) to isolate systematic gyro bias/scale-factor error from
      stochastic IMU noise before the main pipeline runs (§12, AMR domain)
IMU (accel+gyro, 200Hz)
  → gravity-align, device→vehicle frame
  → ✦ on-manifold preintegration (Forster et al. / GTSAM-style) between
      filter updates instead of naive Euler propagation — cheap upgrade,
      analytic bias-Jacobian re-linearization (§12, SLAM domain)
  → CNN+GRU front end (DeepOdo/DeepOri architecture, §1.1)
      → velocity + attitude pseudo-measurements
  → Motion Bank (GNIO, §1.2) — extended: re-weight prototype retrieval
      by current speed regime, not speed-blind as in the original;
      ✦ consider RelCon-style contrastive pretraining (Apple, self-
      supervised on unlabeled IMU) instead of purely supervised motion
      prototypes (§12, gait domain) — periodicity-agnostic, unlike the
      gait-HMM approach that was checked and does NOT transfer
  → Gated Prediction Head (GNIO, §1.2, Tanh+Softplus config — already
      the paper's own best-validated setting) — extended: gate
      conditioned on speed-MoE router output; ✦ gate strength should be
      a continuously speed/confidence-scheduled Kalman-style gain, not
      a binary on/off switch — borrowed from marine INS DVL-damping-loop
      philosophy (§12, marine domain; note Schuler tuning itself was
      checked and does NOT transfer — timescale mismatch, tunnel
      blackouts are seconds-to-minutes, Schuler period is 84.4 minutes)
  → Speed-MoE Router [NEW] — low/high-speed expert gate, reads
      vibration signature, directly answers GNIO's own diagnosed
      high-speed failure mode; ✦ an FFT-tracked adaptive notch filter
      ahead of this (PX4/ArduPilot-style) is plausible at phone IMU
      rates for quasi-periodic engine/road vibration, though phone
      rates (~100-400Hz) cap which harmonics are trackable (§12, drone
      domain) — RPM-feedback notching does NOT transfer (no RPM source)
  → Nonholonomic InEKF, 21-state SE₂(3) (DMDVDR + AI-IMU-DR lineage,
      §1.1) — extended: Ackermann-steering kinematic constraint folded
      into the loss (GNIO's fix #3 — natural fit since the filter is
      already nonholonomic-aware via AI-IMU-DR)
      ↕ learned Q/R noise adapter (DMDVDR, §1.1, verified code)
  → Outage / Blend Finite-State-Machine — GNSS quality watchdog
      (HDOP + fix-type), covariance-aware re-injection on GPS return;
      ✦ treat the last known-good GPS fix immediately before an outage
      as a hard re-anchor event (tight covariance reset), the AMR-world
      fiducial-marker pattern applied to a vehicle (§12, AMR domain)
  → Position / heading output, no visible jump on re-acquisition
```

**What's genuinely novel (updated after §10-§12 research):**
1. **Speed-conditioned Motion Bank / gate** — GNIO's bank is speed-blind; re-weighting retrieval by current speed regime is the cheapest of its three named fixes to implement. Still not seen elsewhere, domestic or international.
2. **Ackermann kinematic constraint in the InEKF loss** — GNIO's fix #3, applied to a filter that's already nonholonomic-aware via the AI-IMU-DR lineage — a natural fit, not a bolt-on. Still not seen elsewhere.
3. ~~**Outage/Blend FSM**~~ — **retract as a novelty claim.** §10 found `algoarchemist/seamless-navigation` already ships a four-mode hysteresis state machine (GNSS_AIDED→TRANSITION→DEAD_RECKONING→REACQUISITION) with dwell timers and an adaptive `ReacquisitionDriftModel`, field-tested on a real device. Keep the FSM — it's still required — but don't pitch it as our differentiator; pitch the fiducial-re-anchor refinement above (✦) as the specific improvement on top of that pattern instead.
4. ✦ **Continuous confidence-scheduled gating** (vs. GNIO's implicit near-binary soft-ZUPT) — a genuinely new refinement surfaced by the marine-INS cross-domain check, not present in GNIO, DMDVDR, or any competitor repo found in §10.

**Two papers to fold into the core literature review (§1) next revision**, surfaced via the marine-domain cross-domain search rather than the original lit pass:
- **WiCHINS** ("Wheeled and Chassis Inertial Navigation System," arXiv:2601.00275, Jan 2026) — dual-IMU (wheel-mounted + chassis-mounted), three-stage cascaded EKF, vehicle-focused, GNSS-denied. Reports 2.4% drift / 11.4m average error over 228.6 minutes of real driving — a genuine competing/complementary result to DMDVDR's numbers, worth benchmarking against directly. Medium confidence (single automated extraction, not yet cross-verified).
- **PiDR** ("Physics-Informed Inertial Dead Reckoning," arXiv:2601.03040, Jan 2026) — physics-informed residual-learning framework, platform-general (tested on a mobile robot and an AUV, not smartphone/vehicle specifically), reports >29% improvement over baselines. The "physics-informed residual" framing is conceptually close to what Agastya (§10) independently built and to DMDVDR's own residual-correction philosophy — a third independent convergence on the same idea, worth citing as further validation. Medium confidence.

**Deferred/optional:** Mamba backbone (GNIO's fix #1, FDIO-validated elsewhere) — highest effort, treat as a moonshot item (see §9).

---

## 7. Requirement Traceability

| PS requirement | Component | Evidence it works |
|---|---|---|
| Estimate position from MEMS sensors during blackout | CNN+GRU → InEKF | DMDVDR: 0.64% drift over 578m/55s real tunnel |
| Correct sensor bias, drift, vibration noise | Learned Q/R adapter + Gated Head | GNIO ablation: 30.8% RMSE cut from bank+gate alone |
| Detect outage entry / re-acquisition | Outage/Blend FSM | New — no source paper addresses this; standard GNSS-quality watchdog engineering |
| Blend cleanly back to GPS | Covariance-aware re-injection in FSM | New — standard EKF measurement re-injection, sized to avoid visible jumps |
| Hold accuracy over tens of seconds to minutes | Speed-MoE router + Ackermann constraint | Directly answers GNIO's own diagnosed failure mode at vehicle speeds |

---

## 8. Validation Plan

**Primary:** replay an IO-VNBD vehicle sequence with GPS masked through a tunnel-length window — exactly the PS's own wording — and score Absolute Trajectory Error plus drift-rate-vs-outage-duration curves (0-10s, 10-30s, 30-60s, 60s+) against the estimated track.

**Secondary (real-world sanity check):** the GSDC 578m/55s LAX tunnel segment DMDVDR already reports 0.64% drift on — beating or matching that number on the same segment is a concrete, citable claim for a submission.

Report drift as **% of distance travelled**, not raw metres, so results stay comparable across the papers cited above.

---

## 9. Build Plan & Risk

**MVP (must ship):** proven filter fusion — CNN+GRU velocity/attitude front end, nonholonomic InEKF on `ai-imu-dr`'s core, basic outage-detect/blend-back FSM.

**Stretch (the novelty):** GNIO drift suppression — Motion Bank + Gated Prediction Head, Tanh+Softplus gate (already the paper's best config), speed-conditioned bank re-weighting.

**Moonshot (if time allows):** close all three GNIO gaps — Mamba backbone (FDIO-style), low/high-speed Mixture-of-Experts, Ackermann kinematic loss term.

**Biggest real risk:** GNIO and FDIO are both non-peer-reviewed arXiv preprints, 6 and 10 months old respectively at time of research — treat their numbers as promising, not settled science. Lean on DMDVDR's field-tested tunnel result as the credibility anchor in any pitch.

**Second risk:** DMDVDR's own dataset is small (11 sequences, one parking lot) — don't over-claim generalization without testing on IO-VNBD's much larger, geographically diverse set independently.

---

## 10. Live Domestic Competitor Landscape (SIH26168, India, as of 2026-09-04)

A direct GitHub code/repo search (not plain web search, which misses this entirely) found **~14 public repos actively tagged or named for SIH26168**, several with commits from the days immediately before this research — this is a live field, not a hypothetical one. Ranked by verified technical maturity:

**Most technically serious: `krushnasaruk/Agastya`.** Real 4-stage pipeline: sensor sanity/ZUPT gating → classical physics baseline (wheel-speed averaging + gyro heading integration) → `CausalResidualGRU` (verified real `nn.Module`: `Linear(16→64)→GRU(64)→MLP(32→2)`, causal 10-epoch window) predicting velocity/yaw-rate *residuals* → a "SafetyGuard" confidence-gated policy deciding whether to trust the AI correction. No EKF — fusion is direct residual correction. **The single most important data point in this whole landscape**: their own published ablation shows unconstrained "Full AI" correction (2.76m ATE) is *worse* than their classical baseline (1.64m) — only the gated/selective policy narrowly wins (1.61m → 1.42m after INT8 quantization). This independently validates the gating-over-raw-regression architectural bet this dossier already makes (GNIO's whole thesis). 181 passing tests, real IO-VNBD benchmarks.

**Most pedagogically transparent: `tannaakshat447/SIH`.** Stage 1 deliberately runs naive double-integration to document its own catastrophic drift (explicitly notes ">1000% error" as the expected failure mode). Stage 2 adds Butterworth filtering, hysteresis ZUPT, adaptive gyro-bias tracking. Stage 3 has real trained artifacts (`stage3_cnn_gru_model.pt` confirmed present) benchmarking RF/XGBoost/CNN/GRU, settling on a 1D-CNN+GRU hybrid. Same physics-then-learned-residual philosophy as Agastya, arrived at independently — two teams converging on the same architecture family is a meaningful signal.

**Best-engineered pipeline, most honest about ML gaps: `utkarshwrks/PathPulse`** (Team Avinya). 5-stage pipeline (Sense→Condition→Infer→Constrain→Fuse), 1,162 tests, 84.7% coverage, working APK, 10.0% mean drift claimed. Self-admits the actual fusion stage is classical/rule-based, not learned, despite "AI-ML" branding — a useful reminder that a lot of "AI-ML" claims in this field are aspirational rather than shipped.

**Most functionally complete vehicle apps, real device-tested:**
- `Suvrat1629/Zlatan` — most modular codebase (10+ Gradle modules). Uses an adaptive-λ **complementary filter** (not Kalman): `v = (1-λ)(v_blend+dv·dt) + λ·v_absolute`, λ=t/(t+τ). Rigorous dual-threshold ZUPT (accel AND gyro both below threshold, avoiding false triggers on steady cruising). A real bug found in device testing: a hardcoded 30m GNSS-accuracy gate trapped the engine in DR mode for 2h13m during a stationary indoor test — evidence of genuine field testing. Their `.tflite` model is architected but explicitly not shipped; the real GNSS+INS fusion filter "has no design owner yet" per their own plan.md.
- `algoarchemist/seamless-navigation` — tested on a physical Galaxy S24 FE. Implements a **four-mode hysteresis state machine** (GNSS_AIDED→TRANSITION→DEAD_RECKONING→REACQUISITION) with dwell timers, plus an adaptive `ReacquisitionDriftModel` that empirically measures drift and dynamically sizes blend duration. **This is functionally close to the outage/blend FSM this dossier's §6 originally proposed as novel — it no longer is; see the retraction in §6.** Uses a Random Forest (not deep learning) for velocity, deliberately chosen for efficiency; self-reports 4.2× MAE improvement (unverified). Most recently active of all repos found (commits into Sept 2026).

**Most advanced filter/ML math, wrong problem: `harshkumarsingh12/dead-reckoning`.** A genuine 7-state error-state Kalman filter with an explicit velocity scale-factor correction term and triple-gated magnetometer fusion, plus a causal TCN with proper Gaussian-NLL uncertainty — the most rigorous ML formulation found anywhere in the domestic field. But it's confirmed **pedestrian** dead reckoning (README explicitly says so), not vehicle — a real mismatch against the PS as written. The filter/ML design is still worth tracking as adaptable math.

**Weakest despite claims: `sivaraman-tech`.** Has a textbook-correct 8-state EKF, but only as disconnected Python research code — the actual shipped Android app does no dead reckoning at all, just GPS caching with a staleness check. The AI-ML core was never wired into the product.

**Notable outlier: `yuvraj99776600/SIH-winner`** (name is aspirational, not a verified win). Uses accelerometer vibration pattern as a speed proxy — an unusual framing vs. double-integration — and self-reports a real empirical insight: heading/gyro bias dominates the error budget more than speed accuracy. Also self-reports missing its own 10% drift target (37% actual at 60s blackout) — unusually candid.

**Also found, less mature:** `Himanshu121865/sih26168` (surprisingly mature — 45 commits, real `.tflite`/`.onnx` models, claims 4.6m/3.35% accuracy, not deep-dived), `NaviGoo`, `xarjunpatil/SIH26168-...`, `Fatima-yadwad/AI-DR-SIH26168`, `Sahil03344/YatraAI` — early/scaffold stage. `abhyudayraj/Smart-India-Hackathon-26` is empty. Several quick-glance repos (`shreya2707-glitch`, `abidshareef`, `Udaykiran1625`) are bare scaffolds; `Saptarshi2006/sih26168-dead-reckoning` is mislabeled — actually an unrelated full-stack template repo despite its name.

**Overall takeaway:** the field is bimodal — most repos are README-only, but a real top tier (Agastya, PathPulse, tannaakshat447, Zlatan, seamless-navigation) has working code and honestly-reported, sometimes self-critical metrics. The strongest convergence is physics-baseline-plus-gated-learned-correction (not classical EKF-only fusion), and **Agastya's ablation is the most important single fact in this section**: raw ML correction underperforms classical DR; the real engineering challenge — and the place to differentiate — is the gating/confidence logic, not model capacity. Numbers to beat: Agastya's 1.42-1.64m ATE, PathPulse's 10% mean drift.

## 11. International Prior Art (beyond Indian SIH)

Searched specifically for non-Indian work on this same problem — smartphone-only, vehicle-only, GPS-blackout dead reckoning — across four categories.

**Hackathon/competition platforms (Devpost, HackerEarth, MLH, Kaggle): essentially empty.** No project matching this exact problem was found on any of these platforms. The only other Kaggle competition beyond the already-known Google Smartphone Decimeter Challenge is "Indoor Location & Navigation" (WiFi/pedestrian, shopping malls) — not vehicle, not GPS-outage-specific.

**Corporate/vendor developer challenges: also genuinely empty.** Bosch, u-blox, STMicroelectronics, and Qualcomm all sell directly relevant hardware/algorithms (Bosch BHI160BP with onboard PDR, u-blox "Untethered Dead Reckoning" modules, ST's Teseo-VIC3DA automotive DR module explicitly marketed for tunnels/underground parking, Qualcomm "Dead Reckoning 3") but none run a public challenge on this specific topic.

**Academic competition venues: the one real hit.** Japan's AIST runs the **IPIN xDR Challenge**, which explicitly includes a **vehicle dead-reckoning (VDR) track** — tracking forklifts by dead reckoning in real warehouses (2018 edition: 34 people + 6 forklifts over 5 days; continued as "xDR Challenge in Manufacturing" 2020). This is the strongest organized non-Indian, non-hackathon prior art found and worth referencing in a submission for international grounding. Separately, Germany's SPRIN-D "Funke" Fully Autonomous Flight Challenge is a well-funded GNSS-denied navigation competition, but for UAVs using LiDAR+VIO, not ground vehicles or smartphone-only IMU — adjacent domain, different sensor budget.

**Non-Indian GitHub projects: a handful, modest maturity.** `tyu91/mldeadreckoning` — ground-vehicle DR fusing a real IMU+GPS module (not smartphone-only) via a Seq2Seq+DAgger network, ~16 hours of real driving data, reasonably mature independent/capstone-style project. `mbrossar/ai-imu-dr` (France, MINES ParisTech/Safran) — already covered in §2/§4 as core literature. `mtepenner/pnt-dead-reckoning` — early-stage hobbyist project. `Adhithi02/dead_reckoning` — origin unconfirmed (could be Indian-independent, not counted as confirmed international).

**Takeaway:** outside the academic literature and the Indian SIH cluster, there is no active international hackathon or corporate-challenge ecosystem on this exact niche — categories 1 and 3 came back genuinely empty. The one credible organized venue is AIST's IPIN xDR Challenge. This specific combination (smartphone-only + vehicle-only + blackout-to-blackout) is comparatively under-contested internationally relative to the crowded domestic SIH field in §10 — a real, verified gap, not a search miss (deliberately reported as empty rather than padded with tangential results).

## 12. Cross-Domain Technique Transfer

Checked whether techniques from six adjacent fields could strengthen the architecture beyond the core inertial-odometry literature. Findings are folded into §6's pipeline (✦ markers); full technique-by-technique detail below. Two negative results are reported as plainly as the positive ones — a technique that doesn't transfer is still worth knowing wasn't missed.

**1. Robotics/SLAM — on-manifold IMU preintegration.** Forster, Carlone, Dellaert, Scaramuzza, "On-Manifold Preintegration for Real-Time Visual-Inertial Odometry," IEEE TRO 2017 (arXiv:1512.02363), implemented in GTSAM (`ImuFactor`/`CombinedImuFactor`). Condenses high-rate IMU samples between filter updates into a single relative-motion constraint computed correctly on the SO(3)/SE(3) manifold, with closed-form analytic bias-Jacobians so a changed bias estimate corrects the term algebraically instead of requiring re-integration from raw samples. **Verdict: transfers well as a propagation-step upgrade** — better rotation consistency, cheaper bias re-linearization — but doesn't bound drift itself; that's still the nonholonomic constraint's job, since there's no camera for loop closure here.

**2. Drone/UAV — vibration-adaptive notch filtering.** PX4's `gyro_fft` module and ArduPilot's Harmonic Notch Filter track the dominant vibration frequency (via onboard FFT or ESC RPM feedback) and adaptively notch it out of gyro/accel data before it reaches the estimator. **Verdict: partially transfers.** The FFT-tracked variant is plausible for phone-mounted engine/road vibration, though phone IMU rates (~100-400Hz) are far below drone gyro rates (1-8kHz), limiting which harmonics are trackable. The RPM-feedback variant and EKF3 multi-IMU lane-switching do **not** transfer — no RPM source, and a phone has only one IMU to vote with (its underlying principle — innovation-based consistency scoring — is already what the learned adaptive noise covariance is meant to achieve).

**3. Marine/submarine INS — Schuler tuning does NOT transfer; DVL damping-loop philosophy does.** Schuler tuning gives long-duration INS an 84.4-minute natural oscillation period, bounding otherwise-unbounded horizontal drift — but only over trajectories long enough (tens of minutes to hours) for Earth-curvature/gravity-gradient effects to matter. A tunnel blackout (seconds to a few minutes) never completes one cycle; MEMS bias/noise dominates by orders of magnitude at that timescale. **Explicitly considered and rejected, not silently omitted.** What does transfer: marine INS/DVL fusion actively damps error via a Kalman gain *scheduled by aiding-signal quality*, not a hard on/off gate — the nonholonomic zero-lateral-velocity constraint already in this design is functionally a "poor man's DVL," so the genuinely useful borrow is making the ZUPT/nonholonomic correction strength a continuously-scheduled gain (tied to turn radius, wheel-slip proxies) rather than binary gating (folded into §6 ✦).

**4. AR/VR 6DOF tracking — doesn't bound position drift, but the architectural pattern is reusable.** Asynchronous TimeWarp (Carmack 2013; Ha et al., VRST 2016) decouples a slow, accurate pose update from a fast output-extrapolation loop that integrates raw sensor data between corrections — solves display latency, not localization drift, but the "predict-fast, correct-slow" pattern is legitimately reusable for any live position readout, decoupled from the drift problem itself. The original Oculus Rift head-tracking algorithm (LaValle et al., ICRA 2014) is gravity/magnetic-field-anchored orientation correction — strengthens heading (already substantially handled by gravity leveling) but has no positional analog for a phone in a tunnel, so it offers nothing new for the actual hard problem: translational drift.

**5. Industrial AMR/warehouse robotics — UMBmark calibration and fiducial re-anchoring, both useful.** Borenstein & Feng's UMBmark (IEEE T-RA 1996) drives a robot around two opposite-direction square paths to separate *systematic* odometry errors (correctable via one-time calibration) from *non-systematic* ones (stochastic, not correctable that way). **The separation principle transfers well** even though the literal wheel-diameter math doesn't (no wheel odometry on a phone) — a short calibration drive/turn at trip start to isolate gyro bias/scale-factor error is a concrete, cheap addition (folded into §6 ✦). Separately, AGV fleets use fiducial markers (AprilTags) to reset drift at known points rather than eliminating it — the vehicle analog is treating the last known-good GPS fix immediately before a blackout as a hard InEKF re-anchor event, with tunnel/garage geometry as softer map-matching corrections en route (folded into §6 ✦).

**6. Gait analysis/biomechanics — HMM gait-phasing does NOT transfer; contrastive pretraining is a better fit.** HMM-based gait-phase classifiers (Bae & Tomizuka 2010; PMC7917611) rely on a strictly periodic, obligatory phase order (stance→swing→stance) — vehicle motion (straight/turn/brake/idle in arbitrary sequence) has no such structure, so this doesn't transfer. What's closer to a genuine improvement on GNIO's static Motion Bank: Apple's RelCon ("Relative Contrastive Learning for a Motion Foundation Model for Wearable Data," arXiv:2411.18822) — self-supervised contrastive pretraining on large-scale accelerometry, learning motion representations without hand-labeled modes and without assuming periodicity. Folded into §6 ✦ as an alternative to purely-supervised motion prototypes.

**Ranked top findings across all six domains:** (1) UMBmark-style calibration maneuver — cheapest to implement, clearest payoff; (2) continuous confidence-scheduled gating from the marine domain — directly strengthens GNIO's gate design; (3) on-manifold preintegration — a clean propagation-layer upgrade with no real downside. The two honest negatives (Schuler tuning, gait HMM) are worth keeping in the dossier specifically so nobody re-discovers and re-rejects them later.

---

## 12a. The Strategic Hidden Gem — NavIC's Live Operational Crisis

Found by checking current events/institutional context around the PS, not the engineering literature — this is the highest-leverage single finding in this dossier.

**Timeline (all confirmed via news reporting, current as of research date):**
- Mar 2026: IRNSS-1F's atomic clock failed after 10 years, dropping NavIC to 3 operational satellites — below the minimum of 4 needed for an independent fix.
- NVS-02 (launched Jan 2025) never reached operational orbit — a propulsion thruster-valve failure stranded it.
- **31 Jul 2026**: Government officially confirmed in Parliament that "NavIC can no longer independently provide navigation data." Stated reassurance: nearly all real receivers (aviation, shipping, railways, mobile phones) blend NavIC with GPS/Galileo/GLONASS, so users aren't exposed.
- Recovery (NVS-03/04/05) estimated at 15-18 months from an April 2026 baseline — NavIC likely stays degraded through most of 2027.

**Why this matters for SIH26168:** the government's reassurance explicitly assumes some other GNSS constellation is always reachable. That assumption fails precisely in tunnels/underground parking/urban canyons — the PS's exact scenario. No competitor repo (§10) or paper (§1) frames the problem this way; all treat it as a pure ML/filtering exercise. This connection only surfaces by reading current events/institutional context, not arXiv or GitHub.

**Concrete implications:**
1. **Pitch framing** — open the submission with "India's own satellite system can't yet stand alone, and its fallback depends on other constellations being reachable, which fails in exactly the environments this PS names" rather than a generic GPS-blackout framing.
2. **Validates constellation-agnostic design** (already the right call in §6) — but **for a different reason than originally stated here. ⚠ CORRECTION (2026-09-05):** an earlier revision of this section claimed Android's `GnssStatus` has no first-class IRNSS constellation constant. **That was wrong.** `CONSTELLATION_IRNSS = 7` has existed since **API 29 (Android 10)**; `getConstellationType()` and `usedInFix()` expose NavIC satellites and their contribution per-satellite. The error traced to a January 2018 GPSTest GitHub issue that was long since closed — a 2018 issue allowed to stand as a 2026 API fact. See [open-track findings §2.E](SIH26168-open-track-findings.md).
   The design decision is unchanged, on stronger grounds: legacy IRNSS satellites broadcast only L5 + S-band (S-band unusable by phone front-ends), and NVS-01 is the only operational satellite carrying L1 — so **an L1-only phone currently sees exactly one NavIC satellite, a dual-frequency phone at most three**, against the four needed for a fix. NavIC cannot measurably improve position today regardless of API support. Fuse whatever fix quality the chipset reports; surface NavIC separately as instrumentation, not as an accuracy contributor.
3. **New validation scenario for §8**: demonstrate holding position when *no* GNSS constellation has a usable fix (not just "GPS blackout") — the literal condition the government statement describes as currently possible.
4. **Secondary commercial-buyability gem**: India's ride-hailing/delivery fleets (Ola/Uber/Rapido/Swiggy/Zomato) generate a continuous unlabeled IMU+GPS corpus. RelCon-style self-supervised pretraining (§12) on fleet data, fine-tuned per vehicle class, is a licensable product story for Indian mapping/logistics companies independent of an ISRO sale.

Sources: [The Week, "Three satellites short: ISRO's NavIC stops navigating,"](https://www.theweek.in/news/sci-tech/2026/07/31/navic-satellite-navigation-crisis.html) 31 Jul 2026; [Orbital Today, "India's NavIC Satellite Network Faces 15-18 Month Revival,"](https://orbitaltoday.com/2026/04/05/indias-navic-satellite-network-faces-15-18-month-revival/) 5 Apr 2026; [The Week, "NVS-03: India's own GPS prepares a strong comeback,"](https://www.theweek.in/news/sci-tech/2026/08/17/navic-satellite-nvs-03-mission.html) 17 Aug 2026.

---

## 13. Global Technology & Market Landscape

Researched via four parallel passes: NASA/space-agency precedent, China's ecosystem, other major nations, and commercial market analysis. Full detail below; §14 synthesizes this into the actual gap, §15 into a future-tech roadmap.

### 13.1 NASA & space-agency precedent

The strongest pitch-worthy precedent found in this entire research effort: the **Apollo Lunar Roving Vehicle's navigation system** (NTRS 19700026212) — pure odometer+gyro dead reckoning (no GPS, obviously), periodically recalibrated via a sun-shadow device, meeting a **2%-of-distance-traveled accuracy spec over traverses up to ~20km** (Apollo 17, 1972). Same problem shape as SIH26168: continuous cheap dead reckoning, periodically corrected by an external reference — worth using directly in submission framing.

Technically transferable findings: **Maimone, Cheng & Matthies, "Two Years of Visual Odometry on the Mars Exploration Rovers,"** J. Field Robotics 2007 (JPL copy: https://www-robotics.jpl.nasa.gov/media/documents/vo_ras.pdf) — establishes the pattern of an expensive/intermittent higher-fidelity correction (there: stereo VO; here: GPS/map-match) periodically correcting a cheap continuous DR estimate. **Kilic, Gross et al. (WVU, NASA-EPSCoR funded), "Improved Planetary Rover Inertial Navigation... through Periodic Use of Zero-Type Constraints,"** IROS 2019, arXiv:1906.08849, [code](https://github.com/wvu-navLab/corenav) — validates ZUPT/ZARU + nonholonomic constraints on **consumer-grade MEMS sensors** (not tactical-grade) for rover dead reckoning, independent corroboration of the core technique already in §6, from a source with no connection to GNIO/DMDVDR.

Non-transferable but real: Terrain Relative Navigation for Perseverance's landing (camera-to-orbital-map matching, different sensing geometry); NASA's Vision-based Approach and Landing System patent (needs vision, and the PS explicitly forbids camera use).

ISRO's own heritage (pitch-narrative citations, not GPS-denied ground-vehicle technique): a 2025 IEEE SPACE paper applying visual odometry analysis to public Chandrayaan-3 Pragyan rover imagery (third-party academic work, not confirmed as ISRO's operational method — Pragyan's ~105m traverse was largely ground-commanded); the Mars Orbiter Mission's autonomous trajectory correction under 42-minute communication lag, built on Chandrayaan-1 heritage.

### 13.2 China — BeiDou, industry, academia

**BeiDou is healthy and improving** — 50 satellites, BDS-3 core constellation complete since 2020, an Aug 2026 in-orbit upgrade explicitly framed as enhancement (not crisis recovery): open-sky accuracy 1.5-2m, PPP horizontal <0.3m. A genuine, stark contrast to NavIC's documented crisis in §12a.

**China's mapping giants already ship this exact capability at national scale.** Baidu Maps has a named product, "VDR" (AI inertial navigation + sensor-mode detection + historical-trajectory learning), claiming <10% speed-estimation error through tunnels/elevated roads/urban canyons, offered as a public SDK. Amap/Gaode (Alibaba) launched a dedicated smartphone tunnel-navigation solution in 2023, live in 600+ tunnels nationwide, fusing VDR inertial data + road network + mobile network + satellite — their engineering blog states **60% of positioning failures occur in underground parking/tunnels, 30% under overpasses** (a citable real-world-demand statistic). Huawei ADS advertises comparable multi-sensor DR for tunnels/garages, but only marketing material was found, no technical paper.

**Academic honesty check**: Shanghai Jiao Tong's BAT Center reports that even their smartphone IMU-assisted fusion in <4-satellite tunnel conditions only "slightly alleviated severe drift" and remains "insufficient for long-term reliability" — confirms the hard tail of this problem (multi-minute blackouts) stays genuinely open even at a top lab with a shipped-product neighbor (Baidu/Amap) down the road. Wuhan University's LMARS ecosystem (DMDVDR's home) goes deeper than the one known paper — Xiong Hanjiang's group works on smartphone-inertial indoor positioning; WHU's own Geomatics journal has 2020 (LSTM-EKF GNSS/INS) and 2024 (micro-INS+GNSS under 4 visible satellites) vehicle papers.

**China treats this as codified national strategy**, not informal effort: a Jan 2022 government plan targets a "ubiquitous, integrated, intelligent, comprehensive" national PNT system "with BeiDou at the core" by 2027; analysts describe a "PNT resilience triad" (space/BeiDou + terrestrial eLoran + fiber timing); a 2023 Strategic Study of CAE paper (CAS/Tsinghua/CAST authors) frames this under an official "5+1+N" national framework; National University of Defense Technology maintains a dedicated State Key Laboratory of Navigation and Spatiotemporal Technology.

### 13.3 Other nations

**Russia (GLONASS): deteriorating.** 15 of 26 active satellites past their 7-year warranted lifetime as of 2025; GLONASS-K2 modernization delayed to 2030; reported growing dependence on Chinese space infrastructure. No significant published civilian vehicle-DR research found.

**EU (Galileo): healthy** — 27/34 satellites operational, exceeding 2026 performance targets. European automotive DR is chip-based (u-blox ADR modules widely embedded by OEMs; HERE Positioning integrated GiPStech's sensor-fusion engine). Notably, **Horizon Europe funds a dedicated "Quantum Sensors for Inertial Navigation" Grand Challenge** — a real government-funding-level signal this problem category is taken seriously as strategic infrastructure, plus an EGeNiouSS project on vision-augmented navigation for satellite blind spots and a Joint Research Centre "Complementary PNT" initiative.

**Japan:** QZSS expanding from 4 to 7 satellites in 2026 (11-satellite configuration under consideration), providing cm-level CLAS augmentation. Automotive high-precision positioning market projected $340-420M (2026) in Japan alone, driven by Toyota/Honda/Nissan ADAS needing IMU-DR plus multi-constellation GNSS for tunnels/mountains. Beyond the IPIN xDR Challenge (§11), no specific automaker technical whitepaper surfaced.

**South Korea:** Kia has published research testing a hybrid GPS+IMU positioning system specifically on Seoul Metropolitan Area expressway tunnels (doi.org/10.3390/engproc2025102010). No Samsung-specific IMU/chipset work surfaced.

### 13.4 Commercial market analysis

**Sizing (treat as directional only — reports disagree by 10-40x for the "same" category)**: Inertial Navigation Systems market $9.4-13.7B depending on firm (MarketsandMarkets vs. Fortune Business Insights, 2025-2026); "indoor positioning" TAM ranges $14B-$174B across four firms for the same year — a spread wide enough to signal the category isn't cleanly defined by analysts yet, which is itself a market-immaturity signal worth citing as-is rather than picking one number.

**Players and tiers**: a real mid-tier of OEM hardware modules already exists between $1000s tactical INS (VectorNav, Trimble/Applanix) and free phone GPS — u-blox ADR modules, STMicro Teseo-VIC3DA, Bosch BSXlite (all tens-of-dollars, OEM-integration hardware), Teltonika aftermarket trackers (€80-128). **What's absent from every player found: a smartphone-only, zero-added-hardware product** — every commercial solution needs a soldered module or bolted-on tracker.

**Recent funding (2024-2026) is uniformly defense/autonomy-flavored**: Advanced Navigation ($110-158M Series C, Mar 2026), Anello Photonics ($25M + $20M US Army APFIT award for silicon-photonics GPS-denied INS), Inertial Sense (acquired by Hexagon AB, Nov 2025). None target consumer/fleet smartphone-only dead reckoning; none are India-focused.

**MapmyIndia/Mappls**: despite OEM ties (Maruti, JLR, Toyota, Mahindra) and an ISRO/NavIC integration partnership announced in 2021 and still delayed as of 2025, no public statement on dead reckoning or tunnel/GPS-denied continuity was found — a notable silence from India's flagship sovereign mapping company.

## 14. Current Gap Analysis (synthesized)

The technical problem is not unsolved at civilizational scale — §13.2 shows China's Baidu (named "VDR" SDK) and Amap (600+ tunnels, live since 2023) already ship this at national map-app scale. **The actual gap has three parts, and nothing found anywhere in this research hits all three at once:**

1. **National/sovereign gap**: India has no equivalent to Baidu/Amap's shipped tunnel-DR capability. Mappls, despite deep OEM and government ties, shows no public feature in this space.
2. **Vehicle-tier gap**: every commercial DR product (Chinese, European, or otherwise) that was specifically verified targets cars — wheel-tick/CAN-based hardware modules that India's 260M+ two-wheelers (≈75% of the national fleet) mostly can't provide, and no purpose-built solution was found for gig-delivery/ride-hailing fleets (Ola/Uber/Rapido/Swiggy/Zomato/Blinkit) despite them being continuous, high-volume, tunnel/underground-parking-exposed users.
3. **Strategic-timing gap**: NavIC's documented 2026 operational crisis (§12a) creates a live, citable reason India needs a *software-side* resilience story now, independent of hardware satellite recovery timelines (15-18 months minimum).

**Honest caveat, from a top lab with no reason to oversell**: Shanghai Jiao Tong's BAT Center found IMU fusion in real <4-satellite tunnel conditions only "slightly alleviated" drift and remained "insufficient for long-term reliability" — the multi-minute blackout tail of this problem stays genuinely open even next door to a shipped product. Don't pitch this as solved; pitch it as the specific, well-scoped slice (tens of seconds to a few minutes, India's actual vehicle mix) that's achievable now.

## 15. Future Technology Roadmap

**Realistic, 1-3 years**: on-device NPU trajectory (Snapdragon 8 Elite Gen 5, MediaTek Dimensity 9500 already running 3B-parameter models on-device with sub-1.6-bit quantization) is moving toward continuous low-power inference at heavier-than-CNN/GRU scale — the concrete enabler for GNIO's own proposed Mamba backbone (§1.2 fix #1) to become phone-shippable rather than a paper footnote. Mamba's linear-time efficiency is a strong architectural fit for exactly this transition.

**Realistic, India-specific, someone else's timeline**: NavIC's hardware recovery (NVS-03/04/05, Indian-made rubidium clocks replacing the imported ones that failed) reduces the constellation-availability problem over 2027 — worth noting in a submission, but the software has to work regardless of when this lands.

**Complementary, not primary**: 5G-Advanced (Release 18) targets 0.3-2m accuracy in dense urban deployments by ~2027-28 — genuinely useful for urban-canyon degradation, structurally useless in tunnels (no infrastructure). 6G's GNSS-independent positioning vision is speculative/early-standards-stage, realistically 2030+.

**Real but not worth chasing for this project**: quantum inertial sensors (cold-atom interferometry — Sandia, US Naval Research Lab, Imperial College/M Squared all have field-tested prototypes, DARPA-funded via AOSense) remain laser/vacuum-cell systems, fundamentally not phone-scale, likely ever. LEO satellite PNT backups (Xona Pulsar, TrustPoint, operational Iridium STL) are production-ready but target survey/enterprise GNSS chipsets (Trimble, Septentrio, STMicro partnerships), not mass-market phone basebands (Qualcomm/Broadcom) — years away for a phone product, if ever. Both are honest dead ends for this specific product, worth knowing so hackathon time isn't spent chasing them.

---

## 15a. Open-Track Verification Findings → separate file

A verification pass on five proposed "open territory" features plus four supporting research tracks (jamming-vs-blockage discrimination, online self-calibration, tight map coupling, conformal confidence, NavIC, architecture gaps, prior art/patents, IO-VNBD specifics, context classification) lives in its own file:

**→ [SIH26168-open-track-findings.md](SIH26168-open-track-findings.md)**

Headline results, in brief — every proposed feature had prior art the original framing missed, each retains a narrower defensible lane, and each carries a specific implementation trap. Three factual claims were caught and corrected in the process (two of which had propagated into this dossier; see the correction notes in the header and §1.1). Most valuable single finding: a centripetal-consistency loss term giving wheelbase-free speed observability during blackouts. Most strategically valuable: the learned-drift-correction patent lane is genuinely unclaimed.

---

## 16. Sources

1. Qian, L., Lin, X., Niu, X., Huang, Q., Li, L., Guo, G., Wang, Z., Chen, R., ["Avnet: learning attitude and velocity for vehicular dead reckoning using smartphone by adapting an invariant EKF,"](https://link.springer.com/article/10.1186/s43020-025-00168-7) Satellite Navigation, 2025. DOI 10.1186/s43020-025-00168-7 (author order verified via Crossref).
2. [EurekAlert press release on DMDVDR/AVNet](https://www.eurekalert.org/news-releases/1089377) — headline result figures.
3. Feng, Yin, Chen, Qi, Chen, ["GNIO: Gated Neural Inertial Odometry,"](https://arxiv.org/abs/2603.15281) arXiv:2603.15281, 2026.
4. Zhang, Wu, Cao, Zheng, Yang, ["FDIO: Frequency Decomposed Inertial Odometry,"](https://arxiv.org/abs/2511.15645) arXiv:2511.15645, 2025.
5. Chen, Xu, Markham, Trigoni, ["IONet: Learning to Cure the Curse of Drift,"](https://arxiv.org/abs/1802.02209) AAAI 2018.
6. Yan, Shan, Furukawa, ["RIDI: Robust IMU Double Integration,"](https://arxiv.org/abs/1712.09004) ECCV 2018. [Code](https://github.com/higerra/ridi_imu).
7. Herath, Yan, Furukawa, ["RoNIN: Robust Neural Inertial Navigation in the Wild,"](https://arxiv.org/abs/1905.12853) ICRA 2020. [Site](https://ronin.cs.sfu.ca/), [code](https://github.com/Sachini/ronin).
8. Liu et al., ["TLIO: Tight Learned Inertial Odometry,"](https://arxiv.org/abs/2007.01867) RA-L 2020.
9. Brossard, Barrau, Bonnabel, ["AI-IMU Dead-Reckoning,"](https://github.com/mbrossar/ai-imu-dr) code repository (MIT).
10. Wang, Weng, Qu, Ding, Chen, "A Novel Deep Odometry Network for Vehicle Positioning Based on Smartphone," IEEE Trans. Instrumentation and Measurement, vol. 72, 2023, DOI 10.1109/TIM.2023.3240227.
11. ["Glow in the Dark: Smartphone Inertial Odometry for Vehicle Tracking in GPS Blocked Environments"](https://www.researchgate.net/publication/349901602) (VeTorch), 2021.
12. Onyekpe et al., [IO-VNBD dataset](https://github.com/onyekpeu/IO-VNBD), and [accompanying paper](https://arxiv.org/abs/2005.01701), 2020.
13. [Google Smartphone Decimeter Challenge](https://www.kaggle.com/competitions/smartphone-decimeter-2023), Kaggle.
14. DragonEmperorG, [QDeepOdo](https://github.com/DragonEmperorG/QDeepOdo), [QAIIMUDeadReckoning](https://github.com/DragonEmperorG/QAIIMUDeadReckoning), [VDRDataCollector](https://github.com/DragonEmperorG/VDRDataCollector) — repositories, no license file.
15. [Inertial Labs "Tunnel Guide"](https://inertiallabs.com/tunnel-guide-feature-for-gps-aided-ins-improves-performance-during-gnss-outage/) — industrial GNSS-aided INS reference.
16. krushnasaruk, [Agastya](https://github.com/krushnasaruk/Agastya) — CausalResidualGRU + SafetyGuard, real IO-VNBD benchmarks.
17. utkarshwrks, [PathPulse](https://github.com/utkarshwrks/PathPulse) — Team Avinya idea submission + working Android pipeline.
18. tannaakshat447, [SIH](https://github.com/tannaakshat447/SIH) — staged naive-baseline → CNN+GRU progression.
19. Suvrat1629, [Zlatan](https://github.com/Suvrat1629/Zlatan) — adaptive-λ complementary filter Android app.
20. algoarchemist, [seamless-navigation](https://github.com/algoarchemist/seamless-navigation) — GNSS-outage hysteresis FSM + adaptive reacquisition drift model, device-tested.
21. harshkumarsingh12, [dead-reckoning](https://github.com/harshkumarsingh12/dead-reckoning) — ESKF + causal TCN (pedestrian, not vehicle).
22. sivaraman-tech, [AI-ML-based-Intelligent-Dead-Reckoning-System-for-Seamless](https://github.com/sivaraman-tech/AI-ML-based-Intelligent-Dead-Reckoning-System-for-Seamless) — textbook 8-state EKF, unintegrated.
23. yuvraj99776600, [SIH-winner](https://github.com/yuvraj99776600/SIH-winner) — vibration-as-speed-proxy TCN.
24. AIST, [IPIN xDR Challenge](https://unit.aist.go.jp/harc/xDR-Challenge-2020/) — vehicle dead-reckoning competition track, Japan.
25. tyu91, [mldeadreckoning](https://github.com/tyu91/mldeadreckoning) — Seq2Seq+DAgger vehicle DR, real IMU+GPS hardware.
26. Forster, Carlone, Dellaert, Scaramuzza, ["On-Manifold Preintegration for Real-Time Visual-Inertial Odometry,"](https://arxiv.org/abs/1512.02363) IEEE TRO 2017. [GTSAM](https://gtsam.org).
27. ["ArduPilot Harmonic Notch Filter"](https://ardupilot.org/copter/docs/common-imu-notch-filtering.html) / [PX4 gyro_fft](https://docs.px4.io/main/en/config_mc/filter_tuning.html).
28. ["Schuler tuning"](https://en.wikipedia.org/wiki/Schuler_tuning); Savage, ["Schuler Oscillations"](https://www.strapdownassociates.com/Schuler%20Oscillations.pdf) — considered and rejected, timescale mismatch.
29. Borenstein & Feng, ["Measurement and Correction of Systematic Odometry Errors in Mobile Robots"](https://johnloomis.org/ece445/topics/odometry/borenstein/paper60.pdf) (UMBmark), IEEE T-RA 1996.
30. Apple, ["RelCon: Relative Contrastive Learning for a Motion Foundation Model for Wearable Data,"](https://arxiv.org/abs/2411.18822) arXiv:2411.18822, 2024.
31. Ha et al., ["The Asynchronous Time Warp for Virtual Reality on Consumer Hardware,"](https://dl.acm.org/doi/10.1145/2993369.2993375) VRST 2016; LaValle et al., ["Head Tracking for the Oculus Rift,"](https://lavalle.pl/papers/LavYerKatAnt14.pdf) ICRA 2014.
32. ["WiCHINS: Wheeled and Chassis Inertial Navigation System,"](https://arxiv.org/abs/2601.00275) arXiv:2601.00275, 2026.
33. ["PiDR: Physics-Informed Inertial Dead Reckoning for Autonomous Platforms,"](https://arxiv.org/abs/2601.03040) arXiv:2601.03040, 2026.

## Methodology note

Primary sources fetched and read directly where access allowed — GNIO's full PDF read page-by-page from its own rendered figures and tables (high confidence). DMDVDR's Springer page was blocked by a cookie-wall; reconstructed via press release + automated proxy extraction, cross-checked against the authors' own public code for architecture details (headline numbers high confidence, detailed baseline table medium confidence). §10-§12 (live competitor landscape, international prior art, cross-domain transfer) were each researched via independent parallel background agents verifying real file/page contents (GitHub API, raw file fetches, direct paper reads) rather than search-snippet summaries alone — one initial cross-domain agent attempt failed to produce results and was not counted; its replacement sub-agents (and this session's own direct follow-up fetches for the marine/AMR/gait domains and the WiCHINS/PiDR papers) are what's reflected above. No prior SIH solution to this exact problem statement from an earlier year was found; a live, active field of current-year (2026) attempts was found instead and is documented in §10. Anything not independently confirmed is flagged inline above rather than stated as settled fact — re-verify before quoting a specific number in a submission.
