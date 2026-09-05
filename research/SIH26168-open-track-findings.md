# SIH26168 — Open-Track Verification Findings

**What this is:** results of a dedicated verification pass on five proposed "open territory" features plus four supporting research tracks, run 2026-09-05 after a collaborator flagged two factual errors in the main dossier. Each track was researched under instructions to be *skeptical of the proposal's own premises* rather than to confirm them.

**Relationship to other files:**
- [SIH26168-dead-reckoning-research.md](SIH26168-dead-reckoning-research.md) — the baseline dossier (papers, competitors, market, architecture). This file supersedes its §15a.
- [../PLAN.md](../PLAN.md) — the build plan. §4 below lists the revisions this pass forces.

**Confidence convention:** "verified" = read from a primary source directly (paper full text, official API docs, repo file). "reported" = found via a credible secondary source but not independently confirmed. Anything not marked is inference and is labelled as such.

---

## 0. Executive Summary

**The headline pattern, and it held across every completed track: each proposed feature had substantial prior art the original framing missed, each retains a narrower defensible lane, and each carries a specific practical trap that would otherwise have surfaced mid-implementation.**

That is a good outcome, not a bad one. A submission that names its own prior art and demonstrates engineering around the known traps is materially stronger than one claiming invention and getting caught by a judge who knows the field. Every "this is novel" claim below has been downgraded to a specific, defensible, narrower claim.

| Track | Original claim | Reality | Verdict |
|---|---|---|---|
| **A** — Jamming vs. blockage | "Zero coverage in the literature" | Prior art exists (J911 2018; Google ships it in GnssLogger). Stated discriminator is the *wrong* one. AGC goes silent in tunnels. | **BUILD, reframed + reduced** |
| **B** — Online self-calibration | "Genuinely absent from all three papers" | AVNet already estimates bias, mounting rotation *and* lever arm online. Published prior art (OSS-Transformer 2024). | **BUILD NARROW — reframe hard** |
| **C** — Tight map coupling | "Every plan treats map-matching as post-hoc" | Published 2008 (Fouque/Bonnifait). Dead inside parking garages. | **BUILD heading-only, gated** |
| **D** — Conformal confidence | "Statistically guaranteed" | Exchangeability violation makes the guarantee void on trajectories. But raw EKF covariance is *also* overconfident. | **BUILD reduced form; never say "guaranteed"** |
| **E** — NavIC advantage | ISRO-relevance differentiator | API support is real (**this project's earlier "no IRNSS constant" claim was wrong**). But only 1–3 NavIC satellites are usable by a phone vs. 4 needed for a fix. | **BUILD as instrumentation, not accuracy** |
| **F** — Ackermann / MoE / Mamba | Three future-work items | Ackermann yields a genuinely valuable wheelbase-free speed observation. MoE circularity is solvable. Mamba is architecture-chasing at this scale. | **BUILD 2 of 3; gate the third on a test** |
| **G** — Prior art / patents | "Shallow pass previously" | No prior-year SIH match. **The learned-drift-correction patent lane is genuinely open** — every verified in-force phone-DR patent is Kalman-based with no ML, and the closest learned claim is abandoned. India's landscape is empty. | **STRATEGIC ASSET** |
| **H** — IO-VNBD specifics | "Only surface-level figures known" | Full schema recovered. **Headline benchmark is not reproducible smartphone-only.** | **Constraint, not feature** |
| **#2** — Context classification | "None of the three papers attempt it" | Standard in GNSS literature since Gao & Groves. But surfaced a higher-priority fix. | **BUILD innovation gate first** |

**Single most actionable finding:** the centripetal-consistency loss term (Track F) — `L_cent = ‖a_y − v̂·ω_z‖²` — turns every turn during a blackout into an independent speed observation from directly measured quantities, with no wheelbase parameter required. See §2.F.

**Single most dangerous assumption caught:** AGC becomes unavailable exactly when GNSS signals are blocked — i.e. in the tunnel scenario that is the feature's primary target. See §2.A.

**Single most strategically valuable finding:** every in-force patent found in the phone-in-vehicle dead-reckoning space is deterministic/Kalman-based with no machine learning, and the one closest learned claim was abandoned — the learned-drift-correction lane is genuinely unclaimed, and India's landscape in this space is empty. See §2.G.1.

---

## 1. Corrections Applied (Step 0)

Three factual errors, all now fixed in the dossier.

1. **Author attribution — CORRECTED.** AVNet/DMDVDR was cited as "Wang et al." The true first author is **Qian** (Long Qian, Xinchuang Lin, Xiaoguang Niu, Qihai Huang, Leilei Li, Guangyi Guo, Zexin Wang, Ruizhi Chen). *Verified independently via Crossref metadata for DOI 10.1186/s43020-025-00168-7.* The cause was confirmed too: the separate 2023 DeepOdo paper genuinely is "Wang, Weng, Qu, Ding, Chen," and the two bylines cross-contaminated. Fixed in dossier §1.1 and its source list; PLAN.md never carried the error.
2. **Fake-verbatim PS quote — CORRECTED.** A paraphrase sourced from a third-party summary site was presented in quotation marks as official ISRO text. Downgraded to a flagged paraphrase pending the real PS text.
3. **A third bad claim, caught during this pass.** The "~15% reliability improvement" attributed to arXiv:2505.01810 does not exist — 15 is that paper's *generalization gap* (≈100% train vs ≈85% test accuracy). The paper is also Wi-Fi-only (UJIIndoorLoc RSSI), not Wi-Fi/BLE. *Verified by direct read.*

**Pattern worth internalising:** all three errors occurred where a plausible-sounding, specific-sounding claim went unchecked. Two arrived with enough surrounding detail to look verified. The mitigation is procedural, not attentional — verify at the point of citation, not at the point of doubt.

---

## 2. Per-Track Findings

### Track A — GNSS jamming vs. physical blockage discrimination

**Verdict: BUILD, but reframed and scope-reduced.** *(Confidence: high — Android docs and papers read directly.)*

**Android API reality:**

| API | Status | Notes |
|---|---|---|
| `GnssStatus.getCn0DbHz(int)` | API 24, stable | Universally populated, 10–50 dB-Hz typical. **Safe foundation.** |
| `GnssMeasurement.getAutomaticGainControlLevelDb()` | API 26, **deprecated API 34** | Superseded — do not build on this |
| `GnssMeasurementsEvent.getGnssAutomaticGainControls()` | API 33 | **The live path.** Carries level-dB + carrier frequency + constellation |

Permissions: `ACCESS_FINE_LOCATION` only. No `GnssCapabilities` gate, no Developer-Options toggle. Raw measurements are mandatory on Android 10+ and present on >90% of phones. Since API 31 the app requests full tracking via `GnssMeasurementRequest.setFullTracking()`.

**THE TRAP — design-breaking if missed.** AGC is a field on a `GnssMeasurement`, and the official javadoc states: *"when a GNSS signal is too weak to be acquired, the AGC value is not reported."* **In a tunnel — the feature's primary positive class — the legacy AGC field goes silent.** Spens et al. (NAVIGATION 69(3)) confirm empirically: *"when signals are blocked, AGC becomes unavailable — preventing distinction between interference versus attenuation."* Whether the API-33 event-level path still delivers AGC with zero tracked measurements is **not documented — bench-test on target hardware before committing.** Mandatory C/N₀-only fallback either way.

**The premise was mis-stated.** The literature's discriminator is the **sign of the AGC change**, not decay shape. Strizic et al.: *"A voltage increase means that satellites are obstructed, thus less power is received, and a voltage decrease indicates interference or jamming that deposits more power into the spectrum."* Blockage *removes* RF energy (gain rises); jamming *adds* it (gain falls). Consistent with AOSP's own javadoc (*"in cases of strong jamming… this value will go more negative"*). The proposed "gradual vs. simultaneous collapse" cue is a plausible secondary feature, not the primary one.

C/N₀ alone is explicitly inadequate — Kriezis et al. (Stanford, NAVIGATION 2026): *"Physical obstructions, scintillation and multipath effects can produce signatures similar to those of jamming."*

**Handset-level caveats:** AGC direction is inconsistent across handsets (some rise, some fall under RFI); chipsets periodically rescale AGC to baseline; thresholds cannot be standardised across chipsets; both AGC and C/N₀ saturate at low jamming power.

**Prior art (directly on point):** J911 (Strizic, Akos & Lo, 2018) — Android app logging per-satellite C/N₀ + AGC, fielded on 15 smartphones at DHS JamX 17. Spens et al. (2022) — four detectors on Pixel 6 / Galaxy S20+, RFI detected at ~5 dB AGC degradation. **Google ships this**: GnssLogger has a Spoof/Jam tab graphing AGC and C/N₀ per constellation, with its own caveat *"This is an experimental feature… does not catch all spoofing and jamming"* — quotable, and worth pre-empting.

**Motivation — honest framing required.** India's documented interference is **aviation, not roads**: ~465 GPS interference/spoofing reports Nov 2023–Feb 2025 concentrated near Amritsar and Jammu; ~2,000 logged at Indian airports since 2023; DGCA now mandates 10-minute reporting and issued a Nov 2025 SOP. Road-level civilian evidence is thin and anecdotal (car-theft rings using jammers). **Do not claim Indian highways are widely jammed — that is not defensible.** Frame the feature as *GNSS-loss cause attribution*: blockage is the overwhelmingly common case DR must handle anyway; jamming is the rare-but-consequential tail.

**Free uncorrelated feature the hypothesis missed:** IMU/odometry consistency. Also available: GNSS-vs-network-location disagreement, GNSS-vs-NTP time skew.

### Track B — Online self-calibration using GNSS as free labels

**Verdict: BUILD NARROW — the novelty claim must be reframed hard or it will be refuted on stage.** *(Confidence: high — AVNet full text read directly.)*

**Most of the proposal is already inside AVNet.** Its 21-D InEKF state estimates online: gyro bias, accel bias, sensor-to-vehicle rotation `R_s^v`, **and** lever arm `p_s^v`. Verbatim: *"the attitude of the sensor is set to R_s^v ∈ G_SO(3), which maps the sensor coordinates to the vehicle coordinates. At the same time, p_v^s ∈ R³ is introduced to represent the lever arm vector."*

Worse for the claim: the learned noise adapter's Q output is indexed over `{ω_s^s, f_s^s, δ_ω, δ_f, R_s^v, p_v^s}` — so the adapter is the learned controller for *how fast the filter re-estimates mounting rotation and lever arm*. Adapting Q on `R_s^v` **is** adapting the mounting-alignment rate. The lineage runs back to AI-IMU (Brossard), which performs explicit "dynamic lever arm calibration."

> **Do not pitch "we estimate sensor bias and mounting alignment online."** A judge who reads AVNet Eq. (5)–(6) refutes it in one question.

**What is genuinely absent from AVNet:** (1) GNSS is never used at runtime — AVNet is inertial-only, GNSS coupling listed as future work; (2) no test-time gradient updates, all training offline. AVNet's own stated limitation: the phone was rigidly fixed during collection, with generalizing across different smartphones named as future work.

> **Defensible framing: GNSS-supervised test-time adaptation across heterogeneous phones and mountings.**

**Prior-art hit:** OSS-Transformer (IEEE T-VT 73(11):16295–16311, 2024) — online semi-supervised GNSS/INS network with online network training explicitly for outage resilience. *Approximately this feature, published, for vehicles.* The differentiator must be smartphone-grade / arbitrary mounting / on-device, not the concept.

**Lane confirmed open:** AirIMU (arXiv:2310.04874) and AirIO (arXiv:2501.15659) do online *uncertainty* only — no online parameter adaptation. Verified against both papers and GNIO's characterisation of them.

**THE TRAP:** these parameters are only observable under **sufficient motion excitation**. A straight, constant-speed highway run into a tunnel approaches the degenerate case — so the last 30–60 s before a blackout, exactly the window the proposal wants to exploit, is often the *worst* window for identifying alignment. Design implication: opportunistically calibrate during turns and speed changes throughout the drive, not in a fixed pre-blackout window.

**Feasibility:** full-network gradient step at 10 Hz is unrealistic on-device (backward ≈3× forward FLOPs). Restricted BatchNorm-affine updates are affordable — TENT (arXiv:2006.10726), UL-VIO (arXiv:2409.13106, "first work to perform noise-robust TTA on VIO"). Note MCUNetV3's finding that last-layer-only adaptation gives limited cross-domain benefit; BN-affine is the better cheap target. RLS/Kalman bias re-estimation is **free** — it is already the InEKF update.

**Cite rather than reinvent:** Wahlström, Skog & Händel, "IMU Alignment for Smartphone-based Automotive Navigation," FUSION 2015 — GNSS-aided simultaneous navigation and smartphone-to-vehicle alignment.

**Guard rails:** frozen backbone + BN-affine only; bounded parameter deltas; small replay buffer (benchmarks show replay > GEM > EWC, with EWC forgetting sometimes *worse* than naive); hard revert to offline weights if the GNSS-supervised loss degrades — necessary because GNSS quality collapses in urban canyons precisely when you would be training on it.

### Track C — Tightly-coupled map constraints

**Verdict: BUILD, heading-only and gated. Do not claim novelty on tight coupling.** *(Confidence: high — Newson & Krumm read directly.)*

**Prior art:** Fouque, Bonnifait & Bétaille (IEEE/ION PLANS 2008) published exactly this — road bearing as a heading observation in a Kalman filter, termed *map-aided odometry*, with innovation gating and conservative fallback to pure DR. Lineage: El Najjar & Bonnifait (Autonomous Robots 2005); Toledo-Moreo et al. (lane-level GNSS/DR/map EKF with integrity monitoring); arXiv:2507.00654 (2025, road-parallel/perpendicular covariance σ²∥/σ²⊥); Gustafsson et al. (2002, particle-filter road constraints). **Name Fouque 2008 before a judge does.**

**Newson & Krumm will not supply the confidence score:**
- Viterbi returns an argmax path, not a normalized posterior — forward-backward would be required, which the paper never runs.
- It *deliberately omits heading*: *"We did not use heading data, mostly because we are assuming we have no compass data from the vehicle."* The proposal inverts this assumption.
- Counter-intuitively, accuracy is **worse at 1 Hz than at 30 s sampling** — *"frequent, noisy points tend to pull the route rather violently in different directions."* A high-rate phone DR feed is the regime HMM matching handles least gracefully.
- Explicit failure documented: when no candidate lies within 200 m the lattice breaks — *"when the vehicle enters a tunnel or an urban canyon."*

**Confidence→R mappings** exist but are always learned or heuristic. Wang et al. (NAVIGATION 70(2), 2023) warns that in low-information map regions the map aid *"might actually impair the performance of the INS integration filter."* OSRM's confidence is unusable — a trace-length heuristic that returns 0 on correct unambiguous matches.

**Elegant finding:** on parallel service roads beside a highway — the classic ambiguity — heading is *identical* across candidates. A heading-only constraint is therefore **safe exactly where a lateral-position constraint is most dangerous.** This is a principled argument for heading-only, not merely a conservative one.

**Parking-garage dead zone — confirmed from OSM's own documentation.** Mappers terminate service roads at `amenity=parking_entrance` because surveying multi-storey aisles is impractical and "GPS cannot cope with layers of concrete." There is no road network to constrain against in one of the PS's named scenarios. Mitigation is free: Newson & Krumm's 200 m no-candidate rule lets the matcher detect this and self-disable.

**Tooling:**

| Library | Exposes candidates/probabilities? | On-device? |
|---|---|---|
| `leuvenmapmatching` | **Yes — best.** Lattice, per-match `logprob`/`logprobe`/`logprobt`, `obs_noise` | Pure Python — prototype only |
| Valhalla Meili | Good. `confidence_score`, `raw_score`, `matched_points` with edge detail, k-best via `best_paths` | **Best.** C++, tiled data explicitly for offline use on memory-constrained devices |
| OSRM `/match` | Weakest — one confidence per matching, no candidate geometry | Server-only, no official mobile build |

**Recommended form:** heading-only; constrain only when all surviving candidates agree in bearing within ~5°; require N consecutive consistent epochs and no junction within lookahead; chi-square innovation gate against gyro-propagated heading; hard-disable on zero candidates or barometer-detected level change. **Never constrain lateral position.**

### Track D — Conformal-prediction confidence

**Verdict: BUILD THE REDUCED FORM. Never use the word "guaranteed."** *(Confidence: high — paper read in full.)*

**Paper identity:** arXiv:2505.01810 is real — *"Conformal Prediction for Indoor Positioning with Correctness Coverage Guarantees"* (Zhou, Peng, Long, 3 May 2025). Its conformal-risk-control extension for path navigation is genuine. Its "15% improvement" as described to us is not (see §1.3). Wi-Fi RSSI only.

**The exchangeability problem is fatal to the strong claim.** The paper has a section titled "The Exchangeability Assumption in Indoor Positioning" — it *flags* the issue, then offers heuristic mitigations (use recent calibration data, normalize signal strengths). That is a caveat, not a method. Its dataset is static survey-point fingerprints, so it never confronts vehicle-grade autocorrelation.

Principled extensions exist; each has a disqualifying catch here:

| Method | What it gives | Why it doesn't rescue the claim |
|---|---|---|
| Non-exchangeable CP (Barber et al., *Ann. Stat.* 2023, arXiv:2202.13415) | Coverage degraded by a *bounded* amount, weighted quantiles shrink the gap | Honest statement becomes "α minus unquantified slack," not α |
| ACI (Gibbs & Candès, arXiv:2106.00170) | No exchangeability needed | Guarantees **long-run** coverage frequency, *not* per-timestep — worthless across a 3-minute demo |
| EnbPI (Xu & Xie, arXiv:2010.09107) | Replaces exchangeability with stationary + strongly-mixing errors | Drifting DR error is non-stationary — even the weaker assumption is strained |
| Weighted CP (Tibshirani et al., NeurIPS 2019) | Handles covariate shift | Requires a *known* likelihood ratio you will not have |

**Calibration reality:** n≈1000 gives realized coverage ≈0.88–0.92 at α=0.1 — but n must be ~1000 **independent routes**, not samples (1000 consecutive samples at 10 Hz is 100 s of one drive; effective n ≈ 1). **Split by route, never randomly** — random splitting leaks autocorrelated neighbours and manufactures fake coverage. IO-VNBD (UK/France/Nigeria) → live Indian demo is unmodelled distribution shift that voids the guarantee regardless.

**But the fallback is not clean either.** EKF covariance in dead-reckoning is documented as systematically **overconfident** — NEES > 1 is the standard diagnostic, driven by observability violations in the linearization. Displaying the raw ellipse is also not honest.

**What to build:** fit a scalar conformal inflation factor on held-out IO-VNBD *routes*, rescaling the EKF ellipse until empirical containment hits target. ~30 lines, reuses existing machinery, demonstrably corrects the NEES>1 overconfidence.

**Language discipline:** say *"empirically calibrated coverage — 90% containment on held-out routes."* Never *"statistical guarantee."* Then pre-empt the judge: name exchangeability yourself as the reason you claim no more, citing Barber et al. 2023 and ACI as the principled extensions. Volunteering the limitation reads stronger than defending an overclaim.

### Track E — NavIC-specific fusion advantage

**Verdict: demonstrable as *instrumentation*, not as *accuracy*. Build a NavIC visibility/health panel; do not claim positioning improvement.** *(Confidence: high — vendor product briefs and AOSP source read directly.)*

> **⚠ THIS TRACK CORRECTED AN ERROR IN THIS PROJECT'S OWN EARLIER RESEARCH.** Dossier §12a previously stated that Android has no first-class IRNSS constellation constant, and used that to justify the constellation-agnostic design. **That claim was stale and wrong** — see below. The design decision stands, but for an entirely different reason.

**API question — YES, unambiguously.** `CONSTELLATION_IRNSS = 7` is defined in AOSP `GnssStatus.java` inside the `@IntDef ConstellationType`, added in **API 29 (Android 10)**. `getConstellationType(int)` returns it per satellite, and `usedInFix(int)` reports per-satellite whether that satellite entered the fix — so an app **can** enumerate NavIC satellites and count how many actually contributed. `GnssMeasurement.getConstellationType()` gives raw per-satellite pseudorange-rate and carrier frequency tagged by constellation.
*Origin of the stale claim:* GPSTest issue #105 (January 2018) reported the constant did not exist. That issue is long closed, and GPSTest's README now lists "IRNSS/NavIC (India)" as supported. **A 2018 GitHub issue was allowed to stand as a 2026 API fact.**
*Genuine limit:* the `Location` object is aggregate. There is no per-constellation position or error breakdown — you get satellite-level membership and used-in-fix status, not "NavIC contributed X%."

**Chipset support (verified from vendor product briefs, not press coverage):**

| Chipset | NavIC support | Note |
|---|---|---|
| Snapdragon 4 Gen 5 | **NavIC (L1 + L5)**, explicitly itemised | Budget tier — strongest mass-market datapoint |
| Snapdragon 6 Gen 5 | NavIC listed; dual-frequency L1/L5 | |
| Snapdragon 8 Elite Gen 5 | NavIC listed; triple-frequency L1/L2C/L5 | Does *not* itemise NavIC bands |
| MediaTek Dimensity 9500 | **NavIC L5 + L1** | |
| Apple | Gated to the "Precision dual-frequency GPS" tier — iPhone 15 Pro / 16 Pro yes; base 15 / 16 **no**; iPhone 17 brings it to the base model | |

**Mandate status:** **no formally notified, in-force mandate exists.** It lives only in ministerial statements (Jan 2025 for 5G devices, Dec 2025 for L1 handsets) after the original 2023 deadline was pushed back under Apple/Xiaomi/Samsung pressure. Treat as policy pressure, not enforceable law — do not describe it as a legal requirement.

**THE DECISIVE DETAIL — why this cannot help accuracy today.** Legacy IRNSS satellites broadcast only **L5 + S-band** (2492.028 MHz, unusable by phone front-ends), and **NVS-01 is the first and only operational satellite carrying L1**. Combined with the constellation being down to three operational satellites (IRNSS-1B, IRNSS-1I, NVS-01):

> **An L1-only phone currently sees exactly ONE NavIC satellite. A dual-frequency phone sees at most THREE.** Four are required for an independent fix.

**Constellation state, verified 2026-09-05:** three operational. IRNSS-1F's clock failed after its 10-year design life. NVS-02 has been stranded in GTO since 29 January 2025 (oxidizer valve failure). **NVS-03 has not launched** — currently at SDSC targeting ~30 September 2026 on GSLV Mk II F18. MoS Space confirmed the ≥4 requirement in Parliament.

**Geometric advantage: plausible, but not demonstrated for Indian urban canyons.** Geometry is 3 GEO (32.5°E / 83°E / 129.5°E) plus 4 GSO at 29° inclination. NavIC-only cannot beat GPS-only (7 nominal satellites vs ~31). Open-sky studies do show GPS+NavIC improves GDOP over India, but **no study was found measuring NavIC vs GPS DOP in Indian urban canyons specifically.** The one multi-GNSS urban-canyon simulation that includes NavIC (MDPI Electronics 14(17):3485) is sited at Gangnam, Seoul — *outside NavIC's ~1500 km service area* — so its NavIC numbers do not transfer. Tellingly, an actual Indian urban DGNSS study over ~300 control points (arXiv:2411.19794) used GPS/GLONASS/Galileo/BeiDou and **excluded NavIC entirely**.
The counter-argument raised earlier stands unrefuted: GEO/GSO satellites sit at fixed azimuth/elevation — predictable, yes, but if a building blocks that bearing it stays blocked, whereas MEO satellites rotate into view. Clustering in a narrow azimuth band is also inherently poor geometric diversity.

**What to build:** a **NavIC visibility/health panel** inside the app — enumerate NavIC SVs, show C/N₀ per satellite, show which entered the fix. It is real, live, uniquely ISRO-relevant, technically honest, and survives expert questioning. A DOP-improvement claim will not survive, in front of judges who know their own constellation is currently below threshold.

### Track F — Architecture gaps: Ackermann, MoE, Mamba

**Verdict: BUILD Ackermann and the MoE routing fix. Gate Mamba on a falsifiable test.** *(Confidence: high — Mamba and AI-IMU-DR read directly.)*

#### F.1 Ackermann as a soft loss term — **the most actionable finding of this pass**

The geometry. True Ackermann requires all wheel axes to meet at one instantaneous centre of rotation: `cot δ_o − cot δ_i = W/L`. Collapsed to the single-track/bicycle model:

```
R = L / tan δ                        (turn radius)
ψ̇ = v·tan(δ)/L = v·κ                 (yaw rate; curvature κ = tan δ / L)
v_lat = 0                            (non-holonomic core)
```
Validity limit: lateral acceleration ≲ 0.5 g, above which tire slip breaks the model (Polack et al.).

Three candidate loss residuals, in increasing order of usefulness:

```
L_nhc  = ‖v̂_lat‖² + ‖v̂_up‖²                    wheelbase-free
L_cent = ‖a_y^measured − v̂_forward · ω_z^gyro‖²   ← THE IMPORTANT ONE
L_curv = max(0, |ω_z| − v̂·κ_max)²               hinge on curvature bound
```

**Why `L_cent` matters:** it couples predicted forward speed to two *directly measured* quantities — lateral specific force and gyro yaw rate. Rearranged, `v = a_y/ω_z`. **Every turn during a blackout becomes an independent speed observation that does not depend on integrating accelerometer noise.** This is the basis of production yaw-rate virtual sensors. **Wheelbase never appears.**

**The wheelbase problem dissolves.** `L` enters neither `L_nhc` nor `L_cent`. `L_curv` needs only a *bound*: passenger cars cluster at L ∈ [2.3, 3.6] m with δ_max ≈ 33°, giving κ_max ≈ 0.28 m⁻¹ (R_min ≈ 3.5–5 m) — one conservative constant covers every car. The friction bound `|v̂·ω_z| ≤ μg` (~0.8 g) is likewise parameter-free and bites hard at speed. If L is wanted explicitly, emit it as a bounded auxiliary head (the "Physics Guard" pattern of Deep Dynamics, arXiv:2312.04374).

**Novelty caveat:** AI-IMU-DR *already* softens its constraints — *"treating them as loose constraints... leads to much better estimates than treating them as strictly null"* — with a CNN predicting the covariance. The real distinction is **inference-time covariance (Brossard) vs. training-time gradient (this proposal)**. A training loss shapes weights so violations are never generated; costs nothing at inference. Closest precedent: PiDR (arXiv:2601.03040), +29% positioning.

**Gate `L_curv` and Ackermann terms off when |a_y| > 0.5 g.**

#### F.2 The MoE circularity — self-inflicted, and solved

Classical MoE gates on the expert's **input**, never its output. Routing on `ŝ` creates a closed autoregressive loop whose failure mode is textbook compounding error — and during a blackout there is no ground truth to correct it.

Four established breakers:
1. **Exogenous router input (primary).** Log-PSD of vertical/longitudinal accel over 1–3 s. Tire-road rolling noise scales logarithmically with speed; wheel rotation appears as a kinematic spectral line at `f = v/2πr` (≈13.4 Hz at 60 mph). Strength check: CarSpeedNet (arXiv:2401.07468) achieves 1.8 m/s RMSE from smartphone accelerometer alone — too coarse for a speedometer, **ample for a binary low/high router** at an 8–10 m/s threshold. Confounds to handle: road surface, tire pressure, mount rigidity, idling-while-stopped.
2. **Soft mixing, not top-1.** Soft MoE (arXiv:2308.00951) avoids routing instability and expert collapse. Domain-native equivalent: the **IMM filter** — mode-conditioned estimates blended by mode probabilities, bounding the cost of a wrong mode.
3. **Hysteresis/dwell.** ~2 s dwell band; supervisory-control theory gives a uniform lower bound on inter-switch times, killing chatter.
4. **Freeze last-known-good GNSS speed** at blackout entry with an age feature — use as a *prior*, not the router.

**Recommendation:** router input = `[log-PSD bands, gyro energy, |a| statistics, last-GNSS speed + age]`, all exogenous; convex soft mixing; ~2 s dwell. If `ŝ` is ever used, `detach()` it so no gradient closes the loop.

#### F.3 Mamba — the paper argues against its use at this scale

Mamba §3.5.1, **Theorem 1**: with N=1, A=−1, B=1, the selective SSM reduces *exactly* to `g_t = σ(Linear(x_t))`, `h_t = (1−g_t)h_{t−1} + g_t x_t` — a gated RNN. **Selection *is* gating, generalized to N-dimensional state.** There is no categorical capability gap over a GRU.

Linear-time is irrelevant at T=200: both GRU and Mamba are O(T) with O(1) recurrent state. Mamba's asymptotic win is over *attention* (O(T²)), and its demonstrated benefits live at 1k–1M tokens.

The only real argument is GNIO's own stated motive — long-range context for constant-speed cruising. A 60 s blackout at 200 Hz is 12,000 samples, genuinely Mamba's regime. But you would downsample or run two rates anyway, and MambaIO still requires a parallel conv branch for only 8–15% error gains.

> **Falsifiable test before any engineering: sweep GRU context length at 1 / 5 / 10 / 20 s.** If accuracy keeps climbing with length until a compute wall, Mamba earns its slot. If it saturates at 2–4 s — the likely outcome — cut it from the plan.

### Track G — Prior art and patents

**Verdict: the learned-drift-correction lane is genuinely open, and India's patent landscape in this space is essentially empty.** *(Confidence: high on patent identities/statuses verified via Google Patents and FreePatentsOnline; medium on Baidu specifics — see access limitation below.)*

#### G.1 Patent landscape — the most strategically useful finding in this pass

**Dense in the general area, thin in the exact niche.** The same Google Patents query (`"dead reckoning" "neural network" "GNSS"`) split by priority window returns **55** results pre-2015 → **510** (2015–2019) → **2,958** (2020+). But narrowing to `smartphone vehicle "dead reckoning" "GNSS" "machine learning" drift` returns **only 4**. Deep-learning inertial odometry for GNSS outages is dominated by *academic literature, not patents* — searches repeatedly surfaced arXiv/MDPI papers where patents would be expected.

**Who holds what:**

| Assignee | Patent | Status | ML? |
|---|---|---|---|
| **STMicroelectronics** | US11199410B2 — DR by determining misalignment angle between movement direction and sensor heading; spec explicitly names GNSS loss, tunnels, urban canyons | Granted 2021-12-14 | **No** |
| **Huawei** | US10900789B2 — mobile device switching to a *vehicle* DR algorithm | Active → 2036 | No |
| **TDK InvenSense** (Trusted Positioning, acq. 2014) | US10018474B2 map-aided portable nav; CA2733032C | Active → 2036 / 2031 | No |
| **Apple** | US20200049837A1 → granted **US11604287B2** — ML model corrects GNSS estimates via Kalman filter | Granted 2023 | Yes |
| **Beijing Baidu Netcom** | US11435186B2 — vehicle DR, tunnel-motivated | Granted 2022-09-06 | No |
| **HERE Global** | US12205326B2 — NN localization, but **image/visual-feature based** | Granted 2025-01-21 | Yes (visual) |
| **Harman (Samsung)** | US11036238B2 — GNSS+DR with geofencing; NN only adjusts geofence radius | Granted 2021-06-15 | Marginal |
| **Qualcomm (via SiRF)** | US6539304B1 — "GPS navigation using neural networks" | **EXPIRED 2020** | Yes |

**The key finding for freedom-to-operate:** the single closest claim found — **US20220228866A1** (Alma Technologies), a *deep neural network trained on IMU data to localize a vehicle without GNSS* — is **ABANDONED**. It is prior art, not a blocker. Combined with the expired Qualcomm/SiRF neural-navigation patent, **the core concept "neural network corrects inertial drift during a GNSS outage" is largely unclaimed.**

> **Every major granted, in-force patent in the phone-in-vehicle DR space that could be fully verified — STMicro, Baidu, InvenSense, Harman, TomTom, Huawei — is deterministic / Kalman-based with no machine learning.** The learned lane is open.

**FTO risks, in order:**
1. **STMicro US11199410B2 — the real mechanical overlap.** It is exactly the phone-in-arbitrary-orientation-inside-a-car problem. Design around it on the *method*: **learn the misalignment rather than computing it via explicit axis determination**, since their claim is tied to explicit axis/SVD-style determination.
2. **Huawei US10900789B2** — narrowly tied to "M consecutive driving-state detections," designable-around.
3. **TDK US10018474B2** — only becomes relevant if map matching is added (which Track C recommends, so note it).
4. **Baidu US11435186B2 — low risk**: claim 1 requires **wheel-speed information**, which a smartphone-only system does not read on.

**India: essentially empty.** No ISRO, IIT, or Jio hits in this space. Closest is TCS EP3165877B1 — *pedestrian indoor* DR, not vehicular. *(Caveat: the Indian Patent Office search is captcha/JS-gated and could not be reached, so India-only unpublished filings are invisible.)*

**Trend evidence for a pitch:** the 55 → 510 → 2,958 filing curve; TDK's 2014 acquisition of Trusted Positioning; Apple's 2018 ML-positioning filing granted 2023; TomTom EP4100699B1 granted 2025-08-20; a Baidu/Honor filing cluster 2019–2021.

*Not verifiable: maintenance-fee/in-force status for FreePatentsOnline-sourced grants (grant dates and 20-year terms imply in force, but fee payment unconfirmed). No litigation evidence found either way.*

#### G.2 Chinese incumbents — what "shipped and working" actually looks like

*(Access limitation: `lbsyun.baidu.com`/`lbs.baidu.com` blocked all fetches; Zhihu and 163.com returned 403. Baidu details below come from search-engine snippets quoting those pages verbatim, not direct reads. Treat Baidu accuracy figures as second-hand.)*

**Baidu 智能定位VDR — confirmed real, but gated.** Documented at `lbsyun.baidu.com` under both the Android location SDK and navigation SDK. Official description: continuous positioning in 丢星 (satellite-loss) scenarios via **"AI惯导 + 位置大数据"** (AI inertial navigation + location big data). Three named techniques: sensor-mode detection, GPS optimization, historical-trajectory machine learning. Claimed **"推算偏差控制在 10% 以下"** — dead-reckoning deviation under 10%. **Phone sensors only — no OBD/CAN anywhere in the docs.** Critically, it is **not usable standalone**: it requires the Navigation SDK, ships as a separate SDK build, and is an *advanced permission you must apply to Baidu for*. Android-first.

**Amap/Gaode — 600+ tunnels confirmed.** Launched March 2023 as "自研VDR惯导增强定位技术," fusing phone sensors + road network + mobile network + satellite. Deployed in 600+ tunnels including Shanghai Waitan and Hangzhou Zizhi. **No accuracy metric has ever been published.**

**The distinction that matters for your pitch — and it cuts both ways:**

*In your favour:* Amap's 600+ tunnels involve **no tunnel hardware**. China has two genuinely separate ecosystems, and press coverage explicitly contrasts them — client-side VDR needing no infrastructure investment, versus deployed beacon/UWB/signal-regeneration systems. The infrastructure track is a *different actor* entirely: Changsha BeiDou Institute rebroadcasts custom BeiDou signals inside a *handful* of named tunnels; Beijing's East 6th Ring uses 500+ in-tunnel transmitters. The scale mismatch (single-digit tunnels vs. 600) confirms Amap is not doing infrastructure.

*Against you:* "600+" is **per-tunnel map/road-network adaptation**, expanding "gradually to all tunnels" — so it is phone-only *sensing* plus tunnel geometry priors, not a universal algorithm. And the premium tier **is** hardware-gated: since June 2025, Amap's long-tunnel *lane-level* navigation (magnetometer + accelerometer + gyro fused on Huawei's edge silicon, sub-metre over 3 km+, ~200 tunnels) is **exclusive to the Huawei Pura 80** — the interface is open to all apps but only on that hardware.

**Neither Baidu nor Amap has published a peer-reviewed paper on their VDR methods** (searched Scholar and arXiv — none found). Their methods are unpublished, which means **AVNet remains the best quotable academic benchmark** — and notably it comes from Wuhan/Chongqing universities, not from Baidu or Amap.

#### G.3 SIH archive

**SIH archive result: no exact prior-year match; SIH26168 appears genuinely new to the programme.** Nearest precedents, all ISRO/Dept. of Space:
- **SIH 2022 SS613** — high-accuracy positioning on mobile/automotive NavIC/GNSS receivers for road lane navigation. Closest analog ever issued.
- **SIH 2022 SS593** — processing/visualisation of raw GNSS data on Android smartphones (same device class).
- **SIH 2022 SS592** — seamless indoor-outdoor navigation (GNSS-denied transition, but pedestrian).
- **SIH 2024 SIH1740** — map-matching to distinguish highway vs. service road using AI/ML (ISRO/SAC).
- **SIH 2023 SIH1520** — NTRIP for NavIC/GNSS RTK corrections.

No PS in 2022–2025 used the words *dead reckoning*, *inertial navigation*, *IMU*, *GNSS outage*, or *tunnel positioning*.

> **⚠ FLAG FOR VERIFICATION: SIH 2026 reportedly carries a companion problem statement, SIH26169, on the same AI-ML dead-reckoning theme.** *(Reported, not verified.)* If real, this materially changes the competitive picture — confirm before finalising positioning.

Winner lists are public for 2023–2025 (team name, PS ID, college, prize) but carry **no solution summaries, abstracts, or code**. The official portal publishes no archived PS lists; only third-party mirrors and SAC/VEDAS retain them.

### Track H — IO-VNBD dataset specifics

**Verdict: this is a constraint on the plan, not a feature.** *(Confidence: high — `README_1.pdf` in the repo read directly; it is the paper plus a 15-page appendix and is the best source, better than the PMC or ScienceDirect versions.)*

**Citation verified:** arXiv:2005.01701 is correct — Onyekpe, Palade, Kanarachos, Szkolnik (Coventry University).

**Schema — vehicle ECU (`V-*.csv`), 29 columns:** GPS satellite count, time since start of day, lat, lon, velocity (km/h), heading, height, vertical velocity, sample period, steering angle, four wheel speeds (rad/s), yaw rate (deg/s), indicated vehicle speed, indicated longitudinal and lateral acceleration (g), handbrake, gear requested, gear, engine speed, coolant temp, clutch position, brake pressure, brake position, battery voltage, air temp, accelerator pedal position.

**Schema — smartphone (`S-*.csv`), 24 columns:** GPS lat/lon/altitude/speed/accuracy/orientation/satellites-in-range, time since start (ms), date, accelerometer XYZ, gravity XYZ, gyroscope yaw/pitch/roll, magnetic field XYZ, orientation yaw/pitch/roll.

**Four parsing gotchas that will otherwise cost hours:**
1. Every column name after the first has a **leading space** — use `skipinitialspace=True`.
2. Files are **not UTF-8** (m/s² and µT arrive as mojibake) — use `encoding='latin-1'`.
3. `GPS SATELLITES IN RANGE` is a **string** like `"27 / 28"`, not numeric.
4. The `V-` header labels accelerator pedal position `(0 or 1)`, but Table 3 and the data (values ~19.0) say **% activation**. The header is wrong.

Plus: the synchronised folder is misspelled in the repo — `Synchronised V abd S datasets` — which will break naive path strings.

**Rates:** VBOX CAN logger and GPS antenna both 10 Hz. Smartphone (AndroSensor) 10 Hz sampling.

> ### ⚠ CORRECTION (2026-09-05) — the 1 Hz GPS claim is wrong
>
> This section previously stated a **1 Hz GPS update** with rows repeating in blocks of ~10. That was read from the paper, not measured. Measuring all 72 S-side files directly (`python/scripts/audit_gps_rate.py`, over 29.7 h and 1,065,249 rows) gives:
>
> | | Claimed here | Measured |
> |---|---|---|
> | IMU sample rate | 10 Hz | **10.00 Hz** ✓ |
> | GPS fix period | 1 s | **9.0 s** median (range 1–13 s) |
> | Rows per fix | ~10 | **89.4** |
> | Sessions consistent with 1 Hz | all | **3 / 79** |
> | Vehicle travel between fixes | ~2.8 m | **27.1 m** median, 70 m max |
>
> The whole dataset contains only **14,212 real position observations**. *(Confidence: high — measured, seeded, reproducible; artifact at `eval/results/gps_rate_audit.json`.)*
>
> **Why the original reading was plausible and still wrong:** a change-detection test on *latitude alone* reports blocks of ~10 on some files. On a near-east/west drive latitude is constant to 6 decimal places for scores of rows while longitude advances at every fix, so latitude-only detection is wrong by an order of magnitude. Detection must use the whole GPS tuple.
>
> **Consequences for evaluation.** A 10 s synthetic outage suppresses roughly *one* real fix and a 30 s outage roughly three. Scoring at 10 Hz against interpolated truth reports interpolation error as estimator error, and between fixes 27 m apart on a curve that is metres. So: score only at rows carrying a real fix, report the actual elapsed time (it can exceed the requested horizon by up to one fix period), and report the truth gap beside every number.

**Three further defects, none previously recorded** *(all measured 2026-09-05; each is now a defended behaviour with a regression test in `python/tests/test_repair.py`)*:

1. **Excel date corruption of the satellite column — 12 of 72 files, 2,118 rows.** Values like `Dec-14`, `Nov-16`, `10-Dec` are Excel's date autocorrect applied to `"12 / 14"`, `"11 / 16"`, `"10 / 12"`: the CSVs were opened in Excel and re-saved. S-Vta28 is 19% corrupted. **The corruption is selective in the worst possible way** — Excel only converts what it can read as a date, needing the first number ≤ 12, so it destroys exactly the rows where fewer than 13 satellites were in the fix, i.e. the degraded-GNSS rows this PS is about. Dropping them biases the dataset away from the condition under test. The transform is exactly invertible (`MMM-DD` → `month / DD`, `DD-MMM` → `DD / month`) and all 48 distinct corrupted forms present invert to `used ≤ visible`, the independent invariant confirming the inversion.
2. **Concatenated recording sessions — 5 files.** `TIME SINCE START` resets toward zero while wall-clock `DATE` continues forward (S-S2: 186311 ms → 10 ms while the date advances 12:06:58.041 → 12:06:59.249). Separate AndroSensor recordings concatenated into one CSV. Split them; integrating across the boundary injects a fabricated 186-second gap. 72 files yield **79 sessions**.
3. **Duplicate timestamp rows — 7 files.** S-Vtb1 has 5,456 duplicate-timestamp pairs across 32,459 rows (17%); 5,370 of them are byte-identical duplicates of the preceding row, so deduplication is safe.

Plus two header hazards not listed below: **CRLF line endings**, and an internal trailing space inside `ORIENTATION (Roll )`.

Uniform across regions; no per-country variation.

**The country question dissolves:** `V-` (ECU) data is **England-only**. Only `S-` (smartphone) data spans England, France and Nigeria — which is the relevant half for a smartphone-only project. Phones used: Huawei P20 Pro, Motorola moto G7 Power, Blackberry Priv, across four vehicles.

**Natural GNSS outages exist but as exclusions, not test cases.** Real receiver dropouts are documented by row index in a txt file (inside the zip archives, not the git tree), there is no tunnel/underpass entry among Table 2's 32 scenarios, and Onyekpe's own code slices *around* these regions as corrupt. With no valid ground truth during a real dropout, you cannot score against it. **All evaluation must use synthetic masking** — which matches the PS's own framing.

**De-facto benchmark comes from WhONet** (arXiv:2104.02581), not the dataset paper. Outages simulated at 10 / 30 / 60 / 120 / 180 s; metrics are CTE (cross-track) and CRSE (cumulative resultant) in metres.

| Outage | WhONet CTE / CRSE | Physics wheel-odometry model |
|---|---|---|
| 30 s | ~0.23–0.55 m / 0.67–1.22 m | 0.84–3.66 m / 2.31–8.24 m |
| 120 s | 1.78 m / **2.62 m** | 1.78 m / 9.11 m |
| 180 s | 0.49 m / **3.93 m** | 2.90 m / 13.67 m |

Headline: 8.62 m error after 5.6 km / 180 s, up to 93% error reduction. **These use wheel-speed sensors, not phone IMU — cite as an upper reference, not a like-for-like target.**

> **⚠ PLANNING CONSTRAINT: the headline WhONet benchmark cannot be reproduced smartphone-only.** Its splits are all `V-` sequences, and `V-St1/St4/St6/St7` and `V-Y2` are marked N/A for smartphone. Since `V-St6`, `V-St7` and `V-S3a` are three of the nine long-outage benchmark sequences, **you must define and document your own S-side split** and state that explicitly in the writeup.

**Repo practicalities:** data-only (the README's claim of "useful python development tools" is false). All CSVs are **Git LFS** — plain `raw.githubusercontent.com` returns pointer stubs; use `media.githubusercontent.com/media/...` or `git lfs pull`. No LICENSE file, but the Data in Brief article (PMC7907232) is **CC BY 4.0** — the defensible basis for use; attribute Onyekpe et al. and cite both versions. `github.com/onyekpeu/WhONet` is reusable for loaders/splits/eval, with two catches: `whonet.py` imports `function_fileswsdisperrcsv2`, which does not exist (the file is `function_file.py`), and it expects all CSVs flat in the working directory.

### Concern #2 — Outage-type context classification

**Verdict: standard in the GNSS literature — claim integration, not invention. And it surfaced a higher-priority fix.** *(Confidence: high.)*

**Prior art is extensive.** Gao & Groves (UCL) built the canonical context-adaptive navigation framework: environmental contexts (indoor/intermediate/outdoor) from satellite count and C/N₀ via SVM + HMM temporal filtering, behavioural contexts from accel/gyro/magnetometer/**barometer** via decision trees and RVMs. >95% pedestrian, >90% vehicle. A dedicated 2020 survey exists (Feriol, Vivet & Watanabe, *Sensors*) with nine context categories. **CAR-EKF** (ION ITM 2023) drives an estimator's Huber-loss hyperparameter from detected context — literally "classify environment → change estimator behaviour." Closest to this proposal: "GNSS Measurement-Based Context Recognition for Vehicle Navigation using GRU" (ION GNSS+ 2023, arXiv:2404.13955) — seven contexts including urban canyon, viaduct-down, shallow/deep indoor; 99.41% isolated, 94.95% transition, 2.14 s transition delay.

**Defensible framing:** novel *relative to the neural inertial-odometry line* (GNIO/FDIO/AVNet), which treats outage as one undifferentiated regime; a known technique *imported* from GNSS literature. Cite Gao & Groves and Feriol yourself.

**Features, in order of evidential support:** satellite count + C/N₀ distribution (the workhorse); satellite azimuth geometry (the GRU paper's "C/N₀-weighted azimuth distribution factor," specifically separating urban canyon from tree-lined avenue and viaduct); per-signal NLOS features (elevation, ΔC/N₀ rate, pseudorange residual — RF/XGBoost reach 93–98.6%); magnetometer (83% indoor/outdoor from magnetic intensity alone); ambient light (real but degraded in dynamic environments, and useless in a pocket or dash mount).

**On the barometer intuition:** using pressure rise on a garage ramp vs. a level tunnel is *plausible and consistent with published use* (Gao & Groves use barometer for behaviour; barometric altimeters distinguish vehicles on vs. under overpasses; Bosch's own white paper covers underground car-park floor detection) — but **no paper validates exactly that discriminator. Present it as a design hypothesis, not a cited result.** Note `Sensor.TYPE_PRESSURE` is absent on some devices; handle absence.

**The higher-priority finding — urban canyon is a different problem.** NLOS/multipath produces >50 m errors *while the receiver still reports a fix*, and 92.5% of code outliers stem from NLOS. The literature's response is measurement-level, not dead reckoning: ML LOS/NLOS classification and re-weighting; Mahalanobis chi-square gating on normalized innovation squared; KF-based RAIM; 3D-mapping-aided GNSS / shadow matching.

> **A single "GNSS lost → switch to INS" FSM never fires in an urban canyon, because GNSS is never lost — it just lies.** That is a concrete, defensible gap against a PS-named scenario. Minimum viable fix: chi-square innovation gate + C/N₀-based measurement de-weighting. **Prioritise this over the context classifier** — fewer lines, no new sensor, closes a gap that exists today.

**Build the rule-based tree, not a learned classifier.** IO-VNBD carries no environment labels (confirmed in Track H), so a learned classifier has no training target without a hand-labelling campaign. Published learned classifiers are only marginally better than thresholds on the same features, and Gao & Groves themselves use decision trees. Concretely: 3–4 states over `(satellite count, mean C/N₀, |Δpressure| over 10 s, speed, loss-onset gradient)` with a few seconds of dwell hysteresis — the GRU paper's 2.14 s transition delay is a realistic benchmark. Roughly a day of work.

---

## 3. Architecture Revisions Forced by This Pass

Against [PLAN.md](../PLAN.md) §2:

| Change | Component | Reason |
|---|---|---|
| **ADD** | `L_cent` centripetal-consistency loss term | Wheelbase-free speed observability from measured quantities (§2.F.1) — highest value per line of code in this pass |
| **ADD** | Chi-square innovation gate + C/N₀ measurement de-weighting | Urban canyon isn't a blackout; current FSM never fires there (§2.#2) |
| **ADD** | GNSS-loss cause attribution (C/N₀ trend + AGC *sign*, event-level API 33) | PS-named requirement; reframed per §2.A |
| **CHANGE** | Calibration timing — opportunistic during turns/speed changes, not a fixed pre-blackout window | Degenerate excitation on straight approach (§2.B) |
| **CHANGE** | Map coupling → heading-only, gated, hysteretic; never lateral | Wrong-match corruption; parallel-road safety argument (§2.C) |
| **CHANGE** | Confidence output → scalar conformal inflation on EKF ellipse, calibrated per-route | Exchangeability voids the strong claim; raw covariance is overconfident (§2.D) |
| **CHANGE** | MoE router → exogenous inputs only, soft mixing, 2 s dwell, `detach()` on `ŝ` | Breaks the circularity (§2.F.2) |
| **DEFER** | Mamba backbone → gated on the GRU context-length sweep | No categorical gap over GRU at T=200 (§2.F.3) |
| **CONSTRAIN** | Evaluation → own documented S-side split; synthetic masking only | WhONet benchmark not reproducible smartphone-only (§2.H) |

---

## 4. Revised Build Plan Deltas

Against [PLAN.md](../PLAN.md) §4. Only the changes are listed.

**Phase 0 additions (data):** handle the four IO-VNBD parsing gotchas and the misspelled folder up front; fetch via Git LFS media URLs; define and document the S-side split explicitly since WhONet's cannot be reused.

**Phase 1 additions (MVP):** add the chi-square innovation gate — it is cheap, closes a real gap, and does not depend on any of the research-heavy features.

**Phase 2 (the differentiators) — revised ordering by verified value-per-hour:**
1. `L_cent` centripetal loss term — highest value, lowest risk, no new sensor
2. GNSS-loss cause attribution — bench-test AGC availability on target hardware **first**; fall back to C/N₀-only if it fails
3. Heading-only gated map coupling
4. Scalar conformal inflation of the covariance ellipse (~30 lines)
5. Rule-based context classifier (~1 day) — only after the above

**Phase 3 (moonshot) — revised:** GNSS-supervised test-time adaptation, restricted to BatchNorm-affine parameters with replay-buffer guarding and hard revert. Mamba only if the context-length sweep justifies it.

**Effort note:** items 1 and 4 above are each well under a day. Item 2's cost is dominated by the hardware bench test, not the code.

---

## 5. Open Questions Log

1. **The PS scenario list is still unresolved.** Two accounts conflict — the verbatim fragment names *urban canyons, dense foliage, tunnels, deep valleys*; a separate account names *tunnel, multi-level parking, dense forested highway, urban canyon*. Possibly two different PS sections (blockage causes vs. test scenarios), but that is a guess. **Full PS text still needed.** This gates the context classifier's target set.
2. **Does event-level AGC (API 33) still arrive when zero satellites are tracked?** Undocumented. Bench test on target hardware. Decides whether jamming detection works in the tunnel case at all.
3. **Does SIH26169 exist** as a companion dead-reckoning problem statement? Reported, unverified. Changes the competitive picture if real.
4. **Track E (NavIC) unresolved** — chipset support, per-constellation API visibility, and whether any measured DOP advantage exists.
5. **Patent landscape and Chinese-incumbent technical depth** — agents still running.
6. **Which demo phone will be used?** Determines AGC availability, barometer presence, and NavIC support simultaneously. Blocks three separate decisions.
7. **Is the barometer garage-ramp discriminator real?** Plausible and consistent with published barometer use, but unvalidated by any paper found. Needs an empirical check on collected data.
