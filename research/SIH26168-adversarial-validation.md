# ShadowNav — SIH 2026 Adversarial Validation

**Scope:** SIH26168 (ISRO) · repo `C:\code\DEAD-RECKONING` @ `77f57e4` · deck `submission/ShadowNav_SIH2026_Idea.pptx` (6 slides, PDF exported) · `eval/results/*.json` · `research/*.md` · `PLAN.md` · Android app · pitch scripts.
**Evaluated:** 2026-09-10. **Stage under evaluation:** SIH 2026 idea submission (see §4).
**Method:** every number below was recomputed from the committed result JSON or read from the repo; rules were checked against the MoE Innovation Cell "SIH 2026 Guidelines" PDF and sih.gov.in/faqs; the PS text was read from a secondary mirror because the official portal text sits behind login. Labels: ✅ OFFICIAL · 🟡 SECONDARY · 🔵 STRATEGIC ADVICE · 🔴 UNVERIFIED. Evidence classes: A demonstrated · B measured · C research-supported · D projected · E unsupported.

---

## 0. Verdict in one screen

**Does it solve the PS?** Partially, and it currently misses the PS's own numeric target by roughly an order of magnitude. The PS (🟡 mirror text, §6) sets *"dead reckoning drift restricted to less than 10% of the total distance travelled"* and illustrates with *"less than 5 metres drift over 50 m GNSS denied"*. ShadowNav's committed median drift is **146% at 10 s, 98% at 30 s, 86% at 60 s, 80% at 120 s, 76% at 180 s** (`eval/results/kinematic.json`, `drift_median_pct`). Only **2.9%–9.4% of the 991 scored outages** meet the 10% target. The deck never mentions the target. An ISRO evaluator wrote that target and will check it first.

**Is the headline claim defensible?** "1.7× to 43× closer than plain sensor maths" is arithmetically true and strategically dangerous. The comparator is unaided double-integration, which no product ships. Against the baseline any judge will think of first — *freeze the last fix* — ShadowNav's estimate is closer than the distance driven in only **13% of 10 s outages and 54% of 30 s outages** (recomputed from `kinematic.json`, `crse_m < distance_m`). At short horizons the app is, on the committed data, worse than a frozen dot. The root cause is known and documented (speed held from a GNSS fix that is up to 9 s stale in IO-VNBD), but the deck does not say it, and no fairer baseline was ever run.

**Is the prototype credible?** The offline pipeline is a genuine, reproducible **LEVEL 5 functional MVP** (161 Python tests, seeded, split published, four real dataset defects found and repaired). The Android app is **LEVEL 4** — it builds, captures at 401 Hz, is parity-proved to 1e-9, but per `android/README.md` *everything downstream of the first GNSS fix is untested on hardware*. There is no recorded drive, no measured blend-back jump, no measured outage-detection latency, no battery or thermal number. The deck screenshot shows the app in `ACQUIRING` (no fix) captioned "Live app".

**Is it differentiated?** The algorithmic core (5-state kinematic EKF, NHC, χ² gate, four-state FSM, critically damped blend) is textbook and, per the project's own dossier, already shipped by at least one domestic competitor. The *defensible* contributions are experimental and engineering: the evaluation-protocol audit (GPS every 9 s, not 1 Hz; Excel date corruption in 12/72 files), empirically calibrated coverage, a parity-tested Kotlin port on a 2.2 MB APK, and honest negative results. Those are real, but they are not what the deck leads with, and the official criteria list "novelty of the idea" first.

**Does the deck communicate?** Visually it is the strongest SIH deck I have audited (skill audit: 0 FAIL / 1 WARN). Its problem is content selection: three PS-required components are absent or marked "next" (OSM map-matching, a locally-running AI speed filter, an edge engine benchmark), one claim is unsupported (two-wheeler capability, evidence class E), and the one number the PS grades on is missing.

**Survival probability (🔵 expert estimate, not a score):** as submitted, this deck is in the top quartile of what the domestic field ships (§12) and will likely clear a college internal round on polish and evidence density. At the ISRO shortlisting it is exposed on three questions any domain scientist will ask in the first minute: *where is your drift versus our 10% target, where is the map-matching we asked for, and where is the AI?* Fixing the framing costs one day; fixing the evidence costs one real drive.

**Five actions before the portal closes (§29 has the full list):**
1. Run two fair baselines — freeze-last-fix and constant-velocity extrapolation — and put them on the slide-4 chart with the PS's 10% line drawn in. (~3 h)
2. Record one real outdoor drive on the moto g64 with the hold-to-simulate-tunnel button, replay the CSV through the Python pipeline, and report the first measured number at 400 Hz IMU / 1 Hz GNSS. This is the single experiment that can change the story. (~1 day)
3. Add the two missing PS components to slide 3 as explicitly-planned boxes (heading-only OSM constraint citing Fouque 2008; gated speed net), and remove "two-wheelers included" from slides 2, 5 and the matrix. (~2 h)
4. Replace the `ACQUIRING` screenshot with one captured in simulated-blackout mode with a fix; fix the "48 satellites in view" caption or produce the log that supports it. (~1 h)
5. Add a "Drift < 10% of distance (PS target)" row to the comparison matrix with an honest ✗ for ShadowNav and the remedy beneath it. Judges reward the team that states the gap before they find it. (~30 min)

---

## 1. Source priority and what was actually verified

| Source | Used for | Status |
|---|---|---|
| MoE Innovation Cell, *SIH 2026 Guidelines* (26-page PDF, Canva, dated 2026-07-29) — fetched from a college mirror `sih-uit.vercel.app`, text extracted | team rules, idea-submission rules, evaluation criteria, dates, IP, prize | ✅ OFFICIAL document, 🟡 mirror copy — confirm the same PDF on sih.gov.in before relying on the 15 Sep date |
| sih.gov.in/faqs (© 2025-26) | team size, female member, same-college rule, two ideas per team, mentors | ✅ OFFICIAL |
| Official template `SIH2026-IDEA-Presentation-Format.pptx` (in repo, verified byte-identical to the download in the prior session) | six-slide cap, pointer text, PDF-only | ✅ OFFICIAL |
| `sih2026.vuce.in/en/ps/SIH26168` — mirror of the PS text | PS wording, requirements, 10% target, scenarios, IO-VNBD mandate | 🟡 SECONDARY — quotes match the collaborator's verbatim fragments in the dossier (10 Hz, OSM, "Advanced Map-Matching & Kinematic Constraints"); pull the official text from the portal and paste it into `research/` |
| Reskilll / lets-code rubric weights | none — reported only | 🟡 not used for any conclusion |
| Repo files, result JSON, git log | every project claim | B / A as marked |

Not found and not invented: an official scoring rubric with weights (none is published), any ISRO-specific evaluation note, any SIH statement on AI-generated content.

## 2. Rule status labels — SIH 2026 rule audit

| Rule / requirement | Status | Source | What to do |
|---|---|---|---|
| Team = 6 students incl. leader; ≥1 female; all from one college | ✅ OFFICIAL | Guidelines p.11; FAQ | Verify roster before nomination; team details "once entered cannot be altered" (p.14) |
| Team name unique and must not contain the institute name | ✅ OFFICIAL | Guidelines p.14 | "ShadowNav" complies |
| Only students selected in the internal hackathon can be nominated; SPOC nominates | ✅ OFFICIAL | p.12 | Internal round is a real gate — the deck must also work for a non-specialist college jury |
| Max 2 PS per team; 500-idea cap per PS, then the PS freezes | ✅ OFFICIAL | p.16 | Submit early; the cap is public on the portal |
| Last date for nomination and idea submission: **15 Sept 2026** | ✅ OFFICIAL (guidelines) vs 🔴 CONFLICT: PS mirror shows "Deadline 30 September 2026" | p.16 vs vuce mirror | Follow the guidelines PDF (authoritative, later-dated) unless the portal itself says otherwise. **Five days from today.** |
| Portal fields: PS, idea title, idea description, idea presentation (PDF) | ✅ OFFICIAL | p.17 | The "idea description" text field is a second deliverable the repo has no draft for |
| Presentation: six slides max incl. title, official template, pointers unchanged, PDF only, delete instructions slide | ✅ OFFICIAL | template slide 7 | Deck complies (6 slides, pointers intact, PDF exported) |
| Evaluation criteria: "novelty of the idea, complexity, clarity and details in the prescribed format, feasibility, practicability, sustainability, scale of impact, user experience and potential for future work progression" | ✅ OFFICIAL (list) · 🔴 weights | p.20 | Design against the list; do not quote any weight as official |
| 4–5 teams per PS may be selected; PS owner "isn't obligated to declare a winner unless student proposals meet their expectations" | ✅ OFFICIAL | p.18, p.25 | ISRO can decline to award. The 10% target is the expectation on record |
| Grand Finale offline at nodal centres, proposed **December 2026** | ✅ OFFICIAL | p.20 | ~12 weeks after shortlisting for the on-device work |
| Mentors: up to 2, ≥5 years' experience, optional, post-shortlisting | ✅ OFFICIAL | p.21; FAQ | Line up a GNSS/INS mentor now |
| Ideas "must be new and must not have been present in any previous event/program of any sort" | ✅ OFFICIAL | p.24 | The repo is private and unpublished — keep it that way until submission; do not enter the same idea elsewhere |
| IP of winning idea split equally with the PS organisation or by mutual agreement | ✅ OFFICIAL | p.24 | Relevant to the "open patent lane" framing in PLAN §1 — ISRO would co-own |
| Prize ₹1,50,000 per PS, paid only if the organisation "likes the idea" | ✅ OFFICIAL | p.25 | — |
| Prototype/demo/video requirement at idea stage | 🔴 none found | — | None officially required; strategically decisive (§20) |
| AI-generated content restriction | 🔴 none found | — | — |

## 3. Evidence classification of the project's headline claims

| Claim (as it appears on the deck) | Class | Basis | Verdict |
|---|---|---|---|
| "Proven on 79 real drives, GPS cut 991 times: 1.7× to 43× closer than plain maths" | **B** | `kinematic.json` vs `baseline_naive.json`, seeded | True; comparator is a strawman (§21) |
| "Already a working 2.2 MB app" | **A/B** | release APK measured 2,226,384 B; runs on moto g64 | True for "runs"; DR path unverified on device |
| "Kotlin core matches the Python reference to 1e-9" | **A** | `ParityTest`, 9 golden cases, 12 tests | True |
| "Any Android 10+ phone" | **D** | minSdk 29 set; one device tested | Compatibility is a build setting, not a test result |
| "Two-wheelers included: 3 of every 4 vehicles" / matrix "Two-wheeler capable ✓" | **E** | IO-VNBD is car data; zero two-wheeler samples; ext-review scorecard gives this axis 1/10 | **Remove or relabel as target** |
| "Honest circle … right 9 times in 10" / "17% → 97% inside" | **B** (with caveats) | `conformal_calibration.json`: raw 17.2%, calibrated 97.2% on test fold | True, but n_test = 34–46 per horizon, coverage is 100% at three of five horizons (over-wide), and the radius in metres is never stated |
| "Optional CNN+GRU speed net: 128 k params, 2.4 ms" | **B** (desktop) / **D** (device) | `inference_latency.json` is single-thread desktop; not wired on device | Chip on slide 3 implies a shipped AI component; it is not in the default path |
| "Slides back … No jump on the map" | **D** | blend implemented and parity-tested; no metric for re-acquisition discontinuity exists in `eval/results` | PS grades on this; **must be measured** |
| "Spots GPS turning unreliable" (χ² gate + C/N₀) | **A** (code) / **E** (effect) | gate exists, gate stats logged; no experiment shows it improves anything on IO-VNBD (no C/N₀ per satellite in the dataset) | Claim the mechanism, not a result |
| "Live app on a moto g64 5G, 401 Hz sensors, 48 satellites in view" | **A** for 401 Hz; **🔴** for 48 satellites | README records `sats 0/0` indoors; screenshot shows `ACQUIRING`; no log of a 48-satellite view in repo | Produce the log or change the caption |
| "NavIC today: 3 working satellites" | **C** | dossier §12a, three news sources (Jul–Aug 2026) | Fine; re-verify the day before submission |
| "Best published car system: 0.6%" (AVNet) | **C** | dossier §1.1, cross-confirmed | Fine, but different dataset, fixed mount, 55 s |
| "Drift 77–108% of distance" (README/scripts) | **B** | `drift_median_pct` | Honest; not on the deck in those words |

## 4. Which SIH stage is being evaluated

| Stage | Officially required | Strategically important | Optional | Unknown |
|---|---|---|---|---|
| **College internal hackathon** (already held or imminent — nomination closes 15 Sep) | Whatever the SPOC set; guidelines only mandate a 15-page report from the SPOC | A deck a non-specialist jury understands in 3 minutes; a demo that visibly does something | Code | Local rubric |
| **Idea submission (this deck)** | 6-slide PDF on template + idea title + idea description text field | Measured numbers, PS-target coverage, a prototype screenshot that shows the feature | Repo link | Whether evaluators open links |
| **Shortlisting** | Expert evaluation on the nine listed criteria | Novelty stated narrowly and defended; feasibility proven | — | Weights; whether ISRO scientists or generalists screen first |
| **Mentoring / preparation** | Attend sessions | Fix the on-device gap | — | Dates |
| **Grand Finale (Dec 2026)** | Working prototype built with mentors at a nodal centre | A real-tunnel drive, live replay, the 10% target hit on at least one scenario | — | Venue, hardware allowed |

Everything below is judged against the **idea-submission** stage unless marked "finale".

## 5. Problem statement forensic analysis

**Text available (🟡 mirror; matches the collaborator's verbatim fragments):**

> Scenario: *"when a vehicle enters a long underground tunnel/ underpass, a multi-level parking lot, a dense forested highway, or a deep urban canyon"* GNSS is lost and navigation apps fail.
> Required components: **Calibration Engine** (phone orientation vs vehicle automatically); **AI Speed Filter** — *"a deep-learning or statistical signal-processing model running locally"* to extract velocity from noisy IMU; **Map-Matching Framework** — offline OSM road network with kinematic constraints; **GNSS+INS Fusion**; **Seamless Transition** — instant switching between GNSS and DR.
> Targets: drift *"less than 10% of the total distance travelled"*; minimum **10 Hz** update on smartphones, ~200 Hz on edge devices; example *"less than 5 meters drift over 50 m GNSS denied"* in under a minute.
> Data: teams *must use the IO-VNBD dataset* for training and validation.
> Deliverables: a working mobile application **and** an edge-deployable software engine.

This resolves the "unresolved discrepancy" in the dossier: the four graded scenarios are **tunnel/underpass, multi-level parking, dense forested highway, deep urban canyon**. Update `research/SIH26168-dead-reckoning-research.md` lines 12–15 and PLAN §7 item 1.

| Question | Answer |
|---|---|
| Actual problem | Consumer navigation on a phone loses position for tens of seconds to minutes when satellites are blocked; the phone has an IMU that could bridge the gap but drifts |
| Pain point of the owner | ISRO/DoS want a software-side, phone-grade resilience capability, framed as AI-ML, validated on a public dataset |
| Why it matters | Long tunnels, underground parking, forested highways, canyons are all common in India; NavIC cannot stand alone in 2026 |
| Primary user | A driver or rider looking at a map app |
| Beneficiary | Same, plus fleets, emergency services |
| Buyer / stakeholder | ISRO as PS owner; downstream a map/fleet company |
| Current workflow | Map app extrapolates or freezes the dot; car units use wheel ticks; phones have nothing |
| Where it fails | IMU-only integration diverges in seconds; speed is unobservable without turns or stops |
| Explicit constraints | phone IMU only; local (offline) processing; 10 Hz min; OSM map-matching; IO-VNBD; drift <10% |
| Implied constraints | any mount orientation; consumer-grade sensors; no cloud in a tunnel; battery |
| Required output | position stream ≥10 Hz through the outage, mode switching, a mobile app, an edge engine |
| Easy to overlook | the map-matching component is *mandatory*, not a nice-to-have; "AI speed filter" is a named module; the 10% target; the 200 Hz edge tier; "dense forested highway" is partial-sky degradation, not total loss |

## 6. Requirement extraction

| Requirement | Explicit / implied | Priority | Our coverage | Evidence | Gap |
|---|---|---|---|---|---|
| Phone IMU-only DR through outage | explicit | critical | 5-state kinematic EKF, gyro-bias state | B | Speed unobservable → 76–146% drift |
| Drift < 10% of distance | explicit | critical | not met (median 76–146%; 3–9% of outages meet it) | B | ~8× short of target |
| Calibration engine (mount orientation) | explicit | critical | `alignment.py` from turns, quality score; stationary detector | B | works in ~84% of runs; not validated on device |
| AI speed filter, running locally | explicit | critical | CNN+GRU trained; opt-in; not on device | B/D | **absent from shipped path** |
| Map-matching framework, offline OSM + kinematic constraints | explicit | critical | none; "heading hint, next" | D | **absent** |
| GNSS+INS fusion | explicit | critical | EKF with position/speed/course updates, χ² gate | A | fine |
| Seamless transition, both directions | explicit | critical | 4-state FSM + critically damped blend | A (code) / E (metric) | no measured jump size or detection latency |
| ≥10 Hz output on phone | explicit | important | 401 Hz IMU, filter runs per sample | A | latency unmeasured |
| ~200 Hz edge engine | explicit | important | pure-Kotlin/JVM core module | A (exists) / D (benchmark) | no edge benchmark |
| Use IO-VNBD for training/validation | explicit | critical | yes, with a defect audit | B | strong |
| Four named scenarios | explicit | important | synthetic masking only; no scenario labels | B (tunnel-like) | no parking / forest / canyon evidence; urban-canyon NLOS handled in design only |
| Working mobile app | explicit | critical | builds, runs, records trips | A | DR path untested past first fix |
| Vibration-noise correction | explicit (title of PS bullet in earlier fragments) | important | none beyond filter noise model | E | not addressed by name |
| Low-end hardware | implied | important | minSdk 29, 2.2 MB, moto g64 | A | battery/thermal unmeasured |
| Any mount orientation | implied | important | alignment | B | — |
| Honest uncertainty | implied | nice-to-have (differentiator) | conformal inflation | B | radius never quantified |

**Critical unaddressed:** map-matching; AI speed filter in the shipped path; the 10% target; blend-back and detection metrics.
**Hidden:** the "idea description" text field; the 200 Hz edge tier; vibration noise by name; "dense forested highway" = degraded-not-lost GNSS (the χ² gate is the right tool — say so).

## 7. Problem–solution fit chain

```
PROBLEM        satellites blocked → dot freezes / jumps
CAUSE          IMU drift; speed unobservable; heading integrates gyro bias
REQUIREMENT    hold position <10% drift; detect outage; blend back; map-match; local AI speed
FEATURE        kinematic EKF + NHC + Ackermann bounds; FSM; blend; conformal ring; (planned) map heading; (opt-in) speed net
MODULE         shadownav-core (Kotlin) ← parity ← python/shadownav
OUTPUT         position @ IMU rate, mode label, 90% radius, trip CSV
BENEFIT        the dot keeps moving in the right direction; the user knows how much to trust it
```

| Feature | PS relevance | User value | Novelty | Complexity | Demo value | Evidence | Keep? |
|---|---:|---:|---:|---:|---:|---|---|
| 5-state kinematic EKF, gyro bias state | 5 | 5 | 1 | 2 | 3 | B | Keep |
| Device-to-car alignment from GNSS-accel correlation | 5 | 4 | 1 (AVNet, Wahlström 2015) | 3 | 2 | B | Keep; don't claim novel |
| Stationary detector (ZUPT with tilt test) | 4 | 4 | 1 | 2 | 4 (visible on desk) | A | Keep |
| NHC + Ackermann friction/curvature bounds | 4 | 3 | 2 | 2 | 1 | B (8-seq: 871 vs 945 m @180 s) | Keep; marginal |
| χ² gate + C/N₀ de-weighting + gate escape | 5 (urban canyon) | 4 | 2 | 2 | 2 | A (code), E (effect) | Keep; measure on a real canyon drive |
| 4-state FSM + critically damped blend | 5 (PS grades it) | 5 | 1 (competitor shipped first) | 2 | 5 | A / E (no metric) | Keep; **measure jump** |
| Conformal inflation of the 90% ring | 3 | 4 | 3 (reduced form) | 1 | 4 | B | Keep; state radius in metres |
| CNN+GRU speed net (GNIO-style) | 5 (named module) | 3 | 3 | 4 | 2 | B (8 seq, bias flips sign) | Keep only if gated and wired; otherwise remove the chip |
| NavIC visibility panel | 2 | 1 | 2 | 1 | 3 (ISRO room) | A (API) | Keep as instrumentation |
| AGC / interference attribution (demo only) | 1 (roads) | 1 | 2 | 2 | 2 | E on device | Keep out of the deck (already is) |
| Filament 3D status orb, bloom, icosphere shards | 0 | 1 | 0 | 5 | 2 | A | **Remove from the pitch; keep out of the APK size story** |
| MapLibre with bundled **Monaco** tiles + demo path | 1 (basemap) | 2 | 0 | 3 | −1 (Monaco in an ISRO demo) | A | Replace tiles with an Indian extent or hide the map in the demo |
| React/Three web MVP replaying a session | 0 (PS wants mobile + edge) | 2 | 0 | 4 | 4 (offline replay is a good demo surface) | A | Keep as demo surface only |
| Trip CSV recording + share | 4 (closes the loop) | 3 | 1 | 1 | 3 | A | Keep — this is how the real drive gets measured |

**AI decoration risk:** the deck's tech chips read "CNN+GRU speed net, opt-in". In an "AI-ML based" PS, an opt-in model that is off by default and not on the phone is the definition of decoration. Either gate it (confidence-gated residual, which is exactly what Agastya's ablation says works) and wire it, or move it to "next" honestly.

**Complexity without value:** the 3D orb pipeline (Filament, `orb.filamat`, `IcosphereGeometry`, `GpuBenchmark`, `RenderTier`) and the Monaco basemap. Roughly a third of the app's Kotlin serves rendering that the PS never asks for, on a project whose selling point is a low-end target. Not a submission blocker; a finale-week distraction.

## 8. Current vs proposed workflow

**Current:** phone map app → GNSS lost → app extrapolates last velocity for a few seconds, then freezes or snaps; car head-units use wheel ticks; India's flagship map vendor has no public DR feature.
**Failure:** no speed source without wheel ticks; heading drifts; re-acquisition produces a visible jump; no honest uncertainty.
**Intervention:** run a calibrated kinematic EKF on the phone's IMU, gate GNSS, blend back, draw a calibrated ring.
**Output:** continuous position and mode label at IMU rate; a trip log.
**Measurable improvement (today):** 1.7×–43× over naive strapdown (B); **unmeasured** against freeze / constant-velocity; **not met** against the PS's 10%.
**Why the existing method fails:** speed unobservability — not heading, on this data: at 10 s the median cross-track error is 17 m but the total error is 180 m; the along-track (speed) term dominates at every horizon (`cte_median_m` vs `crse_median_m`).
**Why this approach is necessary:** the only free speed information is the IMU's vibration signature (learned) and the vehicle's turns (centripetal); both need >10 Hz — which the phone has and the dataset does not.
**What changes after the system:** the dot keeps moving; the user sees a trust radius; the app records the drive so the claim can be checked.

## 9. Novelty audit

| Dimension | Rating | Basis |
|---|---|---|
| Problem framing | MODERATE | "India's NavIC can't stand alone and its fallback assumes another constellation is reachable — which fails in exactly the PS's scenarios" is a framing no competitor uses (dossier §12a). Two-wheeler framing is unsupported by data |
| Algorithm | WEAK | Kinematic EKF, NHC, χ² gating, ZUPT, complementary blend: all textbook (Groves; Fouque 2008; Gao & Groves) |
| Architecture | WEAK–MODERATE | Physics-first with a gated learned residual is the field's convergence point (Agastya, tannaakshat447, GNIO) |
| Workflow | STRONG | Seeded, split-published, defect-audited evaluation; parity-tested port; the trip CSV closes the loop from device to offline metrics |
| Data | STRONG | Four IO-VNBD defects found and repaired with regression tests; the 9 s fix-rate finding invalidates naive 10 Hz scoring that competitors likely use |
| Deployment | MODERATE | 2.2 MB, minSdk 29, no cloud, foreground service; unmeasured on device |
| UX | MODERATE | Calibrated ring, WCAG-measured contrast, 60 dp targets, screen-reader labels — unusual for a hackathon; the ring's size is never stated |
| Integration | WEAK | No map-matching yet |
| Economic model | WEAK | "Free, no SDK" is a feature, not a model; the fleet-data pretraining idea in the dossier is not on the deck |
| Operational model | WEAK | none |

**Separation:** established tech (EKF, NHC, ZUPT, OSM) · known algorithms (χ² gating, conformal inflation, critically damped blend) · known research (AVNet, GNIO, Fouque 2008, Gao & Groves, Barber 2023) · **our implementation** (5-state filter, alignment estimator, stationary detector with tilt test, Kotlin port) · **our integration** (FSM + gate escape + blend + ring on a 2.2 MB app) · **our technical contribution** (heading-only map constraint design — *planned*; gated speed residual — *planned*) · **our experimental contribution** (IO-VNBD fix-rate and corruption audit; drift floor at five horizons; conformal coverage on route-split folds; negative results for accel-speed and centripetal at 10 Hz; speed-net bias sign flip) · **future research** (401 Hz ablations, Mamba/MoE — correctly deprioritised).

**Verdict:** algorithmic novelty is **not sufficiently defensible** and the deck should stop implying it. Experimental and evaluation novelty **is** defensible and should be the innovation story: *"we are the team that measured the dataset before trusting it, and measured our own overconfidence before drawing a circle."*

## 10. Novelty attack test

| Claim | Existing work that challenges it | Domain expert's line | Destroying question | Defence |
|---|---|---|---|---|
| "1.7×–43× closer than plain maths" | Every map app already extrapolates velocity; nobody double-integrates raw accel | "You beat a baseline nobody uses" | *"What is your error versus freezing the last fix?"* | None today. Run it (§21). If ShadowNav loses at 10 s, say so and explain the 9 s GNSS staleness |
| "Honest circle, right 9 in 10" | Barber 2023 non-exchangeable CP; NEES literature | "Coverage of 100% at three horizons means your ring is too big" | *"How many metres is the ring at 60 s?"* | Compute and print it; expect >1 km. Reframe as "never lies small" rather than "actionable" |
| "Learns the phone's quirks while GPS is good" | AVNet online bias + mount + lever arm; OSS-Transformer 2024 | "That's AVNet" | *"What does your calibration do that AVNet doesn't?"* | Nothing yet. Say "implemented, following Wahlström 2015 / AVNet", claim the low-end port |
| "Takes over and hands back smoothly. No jump" | `algoarchemist/seamless-navigation` 4-mode FSM; every commercial unit | "Show me the jump in metres" | *"What is the re-acquisition discontinuity, measured?"* | Not measured. Measure on the 991 outages (position step at first fix after blend) |
| "Two-wheelers included" | No two-wheeler data anywhere in the project | "On what data?" | *"How many two-wheeler drives did you test?"* | Zero. Remove |
| "Spots GPS turning unreliable" (canyon) | Gao & Groves context detection; CAR-EKF; RAIM | "Standard" | *"Did the gate ever reject a real NLOS fix in your tests?"* | IO-VNBD has no per-satellite C/N₀; gate stats exist but no NLOS experiment. Claim mechanism, cite Gao & Groves |
| "Every result re-runs from public data" | Rare in the field | — | *"Can I run it?"* | Yes — 161 tests, seed, `run_mvp.py`. Strong; lead with it |
| "Low-end Android 10+, 2.2 MB" | PathPulse has a working APK | "Fine" | *"Battery per hour? Latency at 400 Hz?"* | Unmeasured. Say so; the phone exists |

## 11. Competitor and substitute research

All rows from the dossier §10–§13 and ext-review §6 (verified 2026-09-04/05); re-check the top three repos for new commits before submission — the field moves weekly.

| Solution | Technology | Target user | Strength | Weakness | Our difference | Valuable? |
|---|---|---|---|---|---|---|
| Baidu VDR SDK / Amap tunnel mode | vendor SDK, car sensors, hardware exclusives | Chinese drivers | shipped at national scale, 600+ tunnels | gated, not phone-only, not India | open, phone-only, Indian | yes — the reference for "solved elsewhere" |
| u-blox ADR / ST Teseo-VIC3DA / Bosch | hardware DR modules with wheel tick | OEM cars | cm-grade | needs a soldered module | zero hardware | yes |
| MapmyIndia/Mappls | OEM navigation | Indian cars | sovereign, ISRO ties | no public DR feature | — | framing only |
| `krushnasaruk/Agastya` (SIH26168) | ZUPT → physics → causal GRU residual → gated SafetyGuard | judges | 1.42–1.64 m ATE (gated), 181 tests, IO-VNBD | metric is ATE on short windows; no app evidence | we have the app + calibrated ring; they have the gated AI the PS asks for | **the strongest domestic rival** |
| `utkarshwrks/PathPulse` | 5-stage pipeline, APK, 1,162 tests | judges | claims **10.0% mean drift** — the PS target | fusion is rule-based, self-admitted | we are more honest about metrics; they hit the number | yes — note the metric definition may differ |
| `algoarchemist/seamless-navigation` | 4-mode hysteresis FSM, RF velocity, S24 FE tested | judges | shipped the FSM first | RF, unverified 4.2× | parity-tested port, calibration | yes |
| `harshkumarsingh12/dead-reckoning` | 7-state ESKF, TCN with NLL | — | rigorous ML | pedestrian | vehicle | low |
| AVNet/DMDVDR (paper) | CNN+GRU → InEKF | research | 0.64% over 578 m tunnel | fixed mount, 11 sequences, no code licence | we run on public data, any mount | the fair benchmark |
| WhONet (paper, IO-VNBD authors) | RNN on wheel odometry | research | 2.62 m CRSE @120 s | wheel speed | phone-only | upper reference only |
| "Freeze the dot" / constant-velocity extrapolation | what map apps do | everyone | free | jumps | **unmeasured** | **must be in the matrix** |

**Capability comparison on the job to be done** (position error through a 60 s blackout, phone-only): AVNet ~0.6% (C) · PathPulse claims 10% (🔴 unverified) · Agastya 1.4–1.6 m ATE (🔴 window unknown) · ShadowNav **86% median** (B). We are the most rigorously measured and, on the published number, the worst. That combination is survivable only if the deck says why (9 s GNSS period in the dataset, speed unobservability at 10 Hz) and shows one on-device number that moves it.

**Why would a user choose us?** No hardware, no SDK, honest uncertainty, runs on a ₹10k phone. **Why not?** The dot is currently no better than a frozen one for the first 30 s. **What they do better:** Agastya's gated AI; PathPulse's headline number. **What we do better:** evaluation rigour, calibration, the parity-proved port, the dataset audit.

## 12. Research gap analysis and references

Top references that should be on slide 6 (currently six papers + dataset + Android API; the deck omits the three that the project's own docs say to cite first):

| # | Reference | Year / venue | Proves | Relation | Limitation | How we address |
|---|---|---|---|---|---|---|
| 1 | Qian et al., *AVNet* — DOI 10.1186/s43020-025-00168-7 | 2025, *Satellite Navigation* | 0.64% over a real 578 m tunnel, phone IMU only | architectural parent; fair benchmark | fixed mount; 11 sequences; unlicensed code | public data, any mount, MIT lineage |
| 2 | Feng et al., *GNIO* — arXiv:2603.15281 | 2026 | gated learned correction beats raw regression; degrades on vehicles | source of the speed-net gate | pedestrian; fails at vehicle speed by its own §V | Ackermann constraint, speed-gated residual (planned) |
| 3 | Onyekpe et al., *IO-VNBD* — arXiv:2005.01701 | 2020; CC BY 4.0 | the mandated dataset | validation | 10 Hz IMU, ~9 s GPS, Excel corruption | audited, repaired, published split |
| 4 | Brossard, Barrau, Bonnabel, *AI-IMU Dead-Reckoning* — arXiv:1904.06064 | 2020, IEEE T-IV; MIT code | NHC + learned Q/R InEKF on KITTI | lineage of the filter | car-mounted IMU | phone-grade port |
| 5 | **Fouque, Bonnifait, Bétaille**, map-aided odometry with road bearing as heading observation | 2008, IEEE/ION PLANS | heading-only map constraint is prior art | the planned OSM component | 2008 receivers | cite before a judge does |
| 6 | **Gao & Groves**, context-adaptive navigation (satellite count + C/N₀ → environment context) | UCL, multiple | urban-canyon = degraded, not lost | χ² gate + de-weighting design | pedestrian-heavy | integrate, don't claim |
| 7 | **Barber, Candès, Ramdas, Tibshirani**, *Conformal prediction beyond exchangeability* — arXiv:2202.13415 | 2023, *Ann. Stat.* | why "guaranteed" is banned | the ring | bound is unquantified here | say "empirically calibrated" |
| 8 | Liu et al., *TLIO* — arXiv:2007.01867 | 2020, RA-L | learned displacement + EKF | lineage | pedestrian | — |
| 9 | Newson & Krumm, HMM map matching | 2009, ACM GIS | matching breaks with no candidate within 200 m — tunnels | self-disable rule for the map component | — | heading-only, gated |

Drop PiDR (arXiv:2601.03040) unless something on the deck uses it; a judge who asks "what did you take from PiDR?" gets no answer today.

**Real research gap:** speed observability at constant-speed cruising with a phone IMU at ≥100 Hz — the 401 Hz ablations are the experiment. **Engineering gap:** gated learned residual on-device; heading-only OSM constraint on-device. **Deployment gap:** battery/thermal/latency on low-end hardware. **User gap:** what a driver does with a 1 km ring.

## 13. Technical architecture audit

| Component | Why it exists | Requirement | If removed | Implemented | Necessary |
|---|---|---|---|---|---|
| `python/shadownav/data` (loader, repair, schema) | IO-VNBD is dirty | data mandate | results unreproducible | yes, tested | yes |
| `evaluation/` (masking, metrics, splits, conformal) | fair scoring | validation | no numbers | yes | yes |
| `filter/ekf.py` 21-state strapdown | the finale-grade filter | 200 Hz edge tier | nothing today (diverges at 10 Hz) | yes, Jacobians FD-verified | keep for 401 Hz re-run |
| `filter/kinematic.py` 5-state | the shipped estimator | DR | no product | yes | yes |
| `filter/alignment.py`, `fsm.py` | calibration, transitions | PS bullets | wrong-frame NHC (4× worse) | yes | yes |
| `models/speednet.py` + `shared/speednet.pt` | the AI speed filter | PS bullet | AI claim becomes empty | trained, opt-in, not on device | must be gated and wired, or downgraded on the deck |
| `shadownav-core` (Kotlin) | edge engine, parity | mobile + edge deliverable | no app | yes, 12 parity tests | yes |
| `app/` sensor capture, GNSS, foreground service, trip CSV | the mobile deliverable | app | — | yes, one device | yes |
| `app/` Filament orb, GPU benchmark, render tiers | aesthetics | none | nothing | yes | **no** — cut from the story |
| `app/` MapLibre + Monaco mbtiles + demo path | basemap | implied UX | a track on a blank canvas | yes | replace tiles; a Monaco map in an ISRO room is a self-inflicted question |
| `frontend/` React/Three web MVP | replay demo | none (PS wants mobile) | lose a good demo surface | yes | keep as demo only |
| `demo/gnss-demo.html` | simulated presentation | none | — | yes | never present simulated as real (README already says so) |
| Security / auth / DB / cloud | none — fully on-device | — | — | n/a | correct: the only permission is fine location |

## 14. AI/ML audit

**Is AI necessary?** For the PS, yes by name ("AI Speed Filter … deep-learning or statistical"). For the physics, only a learned speed source can break the speed-unobservability wall at cruise; the project's own ablations and Agastya's both show raw learned correction hurts and gated helps.

| Item | Value | Evidence |
|---|---|---|
| Model | CNN(6→48→96) + GRU(96) with 32-slot motion bank, 4-head gate, sigmoid | `speednet_training.json` |
| Parameters / size | 128,083 · 0.52 MB fp32 · 0.13 MB INT8 (claimed) | B / D (INT8 not measured on device) |
| Data | IO-VNBD S-side, 64-sample windows @10 Hz; train 5,619 / val 3,423 / test 4,922 windows; route-split | B |
| Labels | GNSS speed, interpolated between fixes ~9 s apart | B — label noise is large and unquantified |
| Metric | test RMSE 1.85 m/s vs trivial 1.98 m/s (−6.5%); MAE 1.44; **bias +1.08 m/s test, −0.28 val** | B |
| Calibration | 1σ coverage 0.27 raw → 0.64 after val-fitted scale | B — still under-covering |
| Effect on position | on 8 test sequences: −9 to −13% CRSE at 30–120 s, **+19% at 180 s** | B (n = 8 sequences, 152 outages) |
| Latency | 2.36 ms median desktop single-thread; ×5 projected = 18.6 ms p95 vs 30 ms budget | B (desktop) / D (device) |
| On device | not wired; no ONNX export committed; NNAPI deprecated → XNNPACK plan | D |
| Explainability | gate weights inspectable; motion bank interpretable | C |
| Failure cases | bias flips sign between folds → driver/phone shift, not fixable from held-out data | B, honestly recorded |
| Drift / robustness | one dataset, three phone models, UK/France/Nigeria roads → India is unmodelled shift | C |

**Agents:** none. Correct.

**Verdict:** a 6.5% RMSE gain over a constant is not an "AI speed filter" a judge can see. Two honest options: (a) wire it behind a confidence gate and show the ablation on the slide including the 180 s loss; (b) present it as *statistical* signal processing (the PS allows either) and make the *centripetal/turn-based speed observation at 401 Hz* the AI-adjacent story after the on-device re-run. Do not leave the chip saying "opt-in".

## 15. Technology stack audit

| Technology | Purpose | Requirement | Why this | Alternative | Why rejected | Implemented |
|---|---|---|---|---|---|---|
| Kotlin, minSdk 29 | app + core | mobile deliverable; NavIC enum lands at 29 | pure-JVM core is parity-testable without a device | C++/NDK | no parity story, more build risk | yes |
| Python / NumPy | pipeline | validation | fast to audit data | MATLAB | licence | yes |
| PyTorch | speed net | AI bullet | standard; `torch.onnx.export` works | TF/TFLite | not installed; conversion untested | trained |
| IO-VNBD CC BY 4.0 | data | mandate | mandated | — | — | yes |
| Filament | 3D orb | none | aesthetics | none | **unexplained on a low-end pitch** | yes |
| MapLibre + mbtiles | basemap | UX | offline by construction | Google Maps SDK | needs network/key | yes (Monaco tiles) |
| React 19 / Three.js / Vite | web replay | none | reuse of demo | plain HTML demo | already exists | yes |
| ONNX Runtime Mobile + XNNPACK | on-device inference | AI bullet | NNAPI deprecated | TFLite | toolchain absent | **no** |
| Valhalla Meili / OSM extract | map-matching | PS bullet | offline tiles, k-best | OSRM | server-only | **no** |

Flag: Filament and Three.js are presentation-value technologies. They are not on the deck (good); keep them off. The deck's chip list is honest, but "moto g64, 401 Hz IMU" is a device, not a technology — replace with "ONNX Runtime (planned)" or "Valhalla/OSM (planned)" to show PS coverage.

## 16. Data audit

| Aspect | Finding |
|---|---|
| Source / availability | IO-VNBD via PMC7907232 mirror, ~202 MB, fetched by script; gitignored | 
| Ownership / licence | CC BY 4.0; attribution present in python/README and slide 6 | 
| Privacy | public research data; the app's trip CSV contains fine location — add a one-line retention statement | 
| Volume | 72 files → 79 sessions, 29.7 h, 1.07 M rows, **only 14,067 real fixes** | 
| Quality | 12/72 files Excel-corrupted (repaired, invertible); 5 concatenated; 7 with duplicate rows; ~9 s GPS period | 
| Labels | no environment labels; no wheel data used (correct) | 
| Bias | UK/France/Nigeria roads, three phones, cars only; no two-wheelers; no tunnels marked | 
| Split | route-level, published `eval/splits/shadownav_s_split.yaml`, seed 20260905 | 
| Reproducibility | strong — 161 tests, seeded, scripts named per result file | 
| If unavailable | mirror is stable; keep a hash of the archive in the repo |

**Can we get it? Yes. Legally? Yes. Reproduce? Yes. Does it answer the PS's question? Only partly** — the 9 s fix period means the dataset cannot show what the phone's 1 Hz GNSS + 400 Hz IMU will do. That is a finding worth one sentence on slide 4; it is currently buried as "slow test data".

## 17. Architecture diagram audit (slide 3)

**Current:** four lanes (Sense → Calibrate and Gate → Estimate → Deliver), seven boxes, chips above, six-step strip below. Native shapes, readable at two depths. Good.

**What is wrong:** (1) the PS's five named components are not visible as such — a judge with the PS open cannot tick them off; (2) map-matching appears only as "map heading hint" in step 6; (3) the AI module is a bullet inside "Position estimator"; (4) no failure path (what happens when alignment quality is low, when the gate escapes, when the map has no candidate); (5) 364 words.

**Corrected layout:**
- **LEFT (inputs):** IMU 401 Hz; GNSS fix + C/N₀ + NavIC — unchanged.
- **CENTER-LEFT (Calibration Engine):** alignment · gyro bias · stationary — one box, titled with the PS's words.
- **CENTER (GNSS health gate):** χ² + C/N₀ → AIDED / DEGRADED / DR / REACQ — unchanged, add "gate escape after 3 rejections" as the failure path.
- **CENTER-RIGHT (Estimator):** kinematic EKF + NHC/Ackermann; **AI Speed Filter** as its own box, labelled "gated residual, next"; **Map-matching (OSM, heading-only)** as its own box, labelled "next, Fouque 2008".
- **RIGHT (Deliver):** calibrated ring; app; **edge engine** (shadownav-core, parity 1e-9) as its own box so the second PS deliverable is visible.
- **BOTTOM strip:** keep, but put the PS 10% target as step 7's success criterion.
- **Remove:** the 12.5 pt italic "plain words" lines on the two input boxes (they are the least informative), the "moto g64" chip.

## 18. Feasibility / viability (🔵 expert strategic scores, 0–10, not SIH scores)

| Dimension | Score | Why |
|---|---|---|
| Technical | 6 | The hard part (speed observability) is unsolved on the data available; the tools to attack it (401 Hz, turn-based speed, gated net) exist and are wired for measurement |
| Operational | 7 | Runs as a foreground service, no network, 2.2 MB; nothing measured for battery/thermal |
| Financial | 9 | Zero hardware, zero cloud, CC BY data, MIT lineage; one phone |
| Deployment | 7 | minSdk 29, R8-shrunk; only one device tested; HIGH_SAMPLING_RATE permission handled |
| Data | 6 | Mandated dataset audited; cannot answer the on-device question; no Indian or two-wheeler data |
| Integration | 4 | No map-matching; speed net not integrated; no ONNX path yet |
| Maintenance | 8 | Tests, golden vectors, seeded results, docs; but `CLAUDE.md` says "no implementation started" and `submission/` is now gitignored while README links to it — fix before any judge opens the repo |
| Government/enterprise | 7 | On-device, no data leaves the phone; IP co-owned with ISRO on winning (guidelines p.24) |

## 19. Prototype audit

**Maturity:** offline pipeline **LEVEL 5** (functional MVP). Android app **LEVEL 4** (partially functional: capture, stationary hold, UI, recording work; the DR-through-blackout path has not executed on hardware with a real fix). Web MVP **LEVEL 3–4** (replays one exported session). Overall **TRL 3–4**: analytical proof on public data plus a component-level breadboard on one phone; TRL 5 needs one instrumented drive.

| Feature | Status | Demonstrated | Tested | Evidence | Priority |
|---|---|---|---|---|---|
| **MUST WORK** | | | | | |
| DR through a masked outage (offline) | done | yes (figures) | 161 tests | `kinematic.json` | — |
| Outage detect → DR → reacquire → blend (offline) | done | in figure | FSM tests | code | measure jump |
| Same on device with a real fix | **not run** | no | parity only | android/README "untested on hardware" | **#1** |
| Alignment on device | not run | no | — | — | #1 |
| Trip CSV → offline replay | code exists | no | — | `TripRecorder.kt` | #1 (it is the measurement path) |
| **SHOULD WORK** | | | | | |
| Calibrated ring on device | done | screenshot shows none (no fix) | assets `conformal.json` | — | #2 |
| Speed net on device | no | no | — | — | #3 |
| Heading-only OSM constraint | no | no | — | — | finale |
| **FUTURE** | | | | | |
| 401 Hz strapdown/centripetal ablations | planned | — | — | — | finale |
| NavIC as measurement | blocked by constellation | — | — | — | — |

## 20. Validation / experiment audit — what must be proven

| Claim | Hypothesis | Baseline | Experiment | Data | Metric | Threshold | Result | Conclusion |
|---|---|---|---|---|---|---|---|---|
| Beats naive strapdown | yes | naive | 991 masked outages | IO-VNBD | CRSE median | >1× | 1.7–43× | **Proven (B)**, weak comparator |
| Beats "freeze last fix" | unknown | error = displacement since last fix | same harness | same | CRSE, % outages won | >50% at every horizon | **not run** | **THIS MUST BE MEASURED BEFORE BEING PRESENTED AS A PROJECT RESULT** — proxy says 13% at 10 s, 54% at 30 s, 78–89% at 60–180 s |
| Beats constant-velocity extrapolation | unknown | last GNSS speed+course held, no gyro | same | same | CRSE | >1× | **not run** | **MUST BE MEASURED** — this isolates the gyro's contribution |
| Meets PS 10% drift | no | — | same | same | drift % | <10% median | 76–146% | **Fails**; state it |
| Seamless re-acquisition | plausible | raw snap | position step at first fix vs blended | same | jump (m), settle time (s) | ≤ ring? define | **not run** | **MUST BE MEASURED** (PS grades it) |
| Outage detection latency | plausible | — | time from mask start to DR state | same | s | <2.14 s (GRU paper benchmark) | **not run** | measure |
| Ring coverage 90% | yes | raw 17% | val-fit λ, test | same | coverage | 0.85–0.95 | 97.2% (100% at 3 horizons) | Proven but over-wide; **print radius in metres** |
| Speed net helps | mixed | ctrl8 | 8 seqs | same | CRSE | — | −13%…+19% | inconclusive; n=8 |
| 401 Hz fixes the 10 Hz negatives | untested | — | one real drive | moto g64 CSV | CRSE, drift % | <10% on any 50 m segment | **none** | the decisive experiment |
| Battery / latency on device | — | — | 1 h drive | device | %/h, ms/sample | — | **none** | measure before finale |

## 21. Metrics — KPIs

| KPI | Definition | Why | Baseline | Target (PS) | Current | Class |
|---|---|---|---|---|---|---|
| CRSE median @10/30/60/120/180 s | ‖est − truth‖ at first real fix after the mask | the field's convention | naive 310 m…63 km | — | 180 / 368 / 640 / 1,071 / 1,474 m | MEASURED |
| Drift % of distance (median) | CRSE / path distance | **the PS's KPI** | naive 229–2,553% | **<10%** | 146 / 98 / 86 / 80 / 76% | MEASURED |
| Share of outages under 10% | count / n | PS pass rate | naive ≈0% | high | 2.9 / 4.2 / 5.5 / 7.3 / 9.4% | MEASURED (this audit) |
| Share of outages beating a frozen dot (proxy) | CRSE < path distance | judge's first question | naive 7 / 6 / 2 / 1 / 0% | >50% | 13 / 54 / 78 / 89 / 83% | MEASURED (this audit, upper bound — true freeze error is displacement ≤ path) |
| CTE median | cross-track | isolates heading | naive 113 m…39 km | — | 17 / 74 / 167 / 344 / 417 m | MEASURED |
| Ring coverage @90% | fraction of truths inside λ·2.146·σ | honesty | raw 17% | 90% | 97% test | MEASURED |
| Ring radius (m) at each horizon | λ·2.146·σ median | usefulness | — | — | **not reported** | UNSUPPORTED |
| Re-acquisition jump (m) | position step at first fix | PS "seamless" | snap | small, no visible jump | **not measured** | UNSUPPORTED |
| Detection latency (s) | mask start → DR | PS "instant" | — | ~2 s | **not measured** | UNSUPPORTED |
| On-device IMU rate | measured Hz | feasibility | — | ≥10 Hz | 401 Hz | MEASURED |
| Filter latency / battery | ms per sample; %/h | low-end story | — | 10 Hz budget | **none** (2.4 ms is desktop) | PROJECTED |
| APK size | release bytes | low-end | — | — | 2.2 MB | MEASURED |

## 22. Demo strategy

**Do not drive live.** Replay committed data; press the tunnel button on a phone that already has a fix.

**60 s:** Slide-2 figure on screen. "GPS cut here (real drive, S-Vw6). Grey: what the car did. Blue: what our app estimated with no GPS for 60 s — 154 m off. Red: plain integration, 3.2 km." Then the phone: hold *Simulate tunnel* on a desk with a fix, show the mode chip go magenta and the ring grow. Stop.

**2 min:** + the web MVP replaying `frontend/public/data/session.json` with the mode timeline, + slide-4 chart with the 10% line and the two fair baselines, + one sentence on why the number is where it is (9 s GNSS in the dataset; 401 Hz on the phone).

**5 min (finale):** the recorded moto g64 drive: CSV → `run_mvp.py` replay → error at exit; the stationary detector on a desk; the NavIC panel; the negative results slide (accel-speed and centripetal at 10 Hz, speed-net bias) — this is the slide ISRO scientists will respect.

| Risk | Fallback |
|---|---|
| No fix indoors → tunnel button disabled | pre-recorded screen capture of the sequence; web replay |
| Projector at 30 Hz trips the demo's auto-degrade | `?tier=high` (demo README) |
| PowerPoint locks the PPTX | present the PDF |
| Judge asks for the repo | README must not point at a gitignored `submission/`; fix `CLAUDE.md` status line |
| Never show live | the 21-state strapdown; the speed net; AGC/interference; anything on Monaco tiles |

## 23. Mentor-guidance validation

| Guidance | Status | Evidence | Change |
|---|---|---|---|
| Evaluator understands the problem | ✅ | slide 2 hook + photos | keep |
| Solution explains what is built | ✅ | slide 3 | add PS component names |
| Explains how it addresses the problem | ⚠ | three icon rows | add the 10% target and where we stand |
| Innovation explicit | ⚠ | "proven on 79 drives", "working app" | those are evidence, not innovation; state the narrow novelty sentence (evaluation rigour + calibrated coverage + low-end port) |
| Technology choices have reasons | ⚠ | chips only | one reason each in the notes or the idea-description field |
| Diagrams simple for non-domain evaluators | ✅ | slide 3 | cut words |
| Feasibility: can it be built | ✅ | built | add on-device caveat |
| Viability: sustainability | ⚠ | "no cloud bill" | say who maintains it after the finale (IP co-owned with ISRO) |
| Risks acknowledged, each with mitigation | ✅ | four pairs | add "two PS components not yet built" as a risk with its plan |
| Impact concrete | ⚠ | "3 in 4 vehicles" | unsupported two-wheeler capability; replace with a number the project can defend (e.g., NavIC 3-satellite status, tunnel count 🔴 needs a source) |
| Real research references | ✅ | six papers | add Fouque, Gao & Groves, Barber |
| AI as assistant, not a replacement for understanding | ✅ | negative results recorded | keep |
| Every statement adds value | ⚠ | slide 3 at 364 words | trim |

## 24. PPT official compliance

**Official structure (✅):** six slides incl. title, fixed titles, pointers unchanged, PDF, instructions slide deleted. **Ours:** six slides, titles intact, footer edited, team oval edited, "IDEA TITLE" replaced with the idea title, PDF exported. **Compliant.** Missing: Team ID (portal), repository link. Extra: none.

## 25. Slide-by-slide forensic audit

**Slide 1 — Title.** Purpose: identification. Judge understands: everything. Weakest: placeholder Team ID. Fix: fill after nomination. **PASS.**

**Slide 2 — "Navigation That Works When GPS Can't".** Strongest element: the real-drive figure with the hidden truth and the error box (154 m vs 3.2 km) — it is honest and legible. Judge understands: a phone app that bridges GPS loss, with a proof figure. May misunderstand: that 154 m is typical (caption corrects it — good); that "two-wheelers included" is tested (it is not); that "1.7×–43×" is against something people use. Unsupported: two-wheeler line (E); "right 9 times in 10" without a radius. Excess: none. Design: the three photos are small and generic; the figure earns its space. Technical: "Plain sensor maths" is a strawman. **Exact fix:** REWRITE innovation row 1 to "Runs on any Android 10+ phone; two-wheelers are the target, cars are the data"; REWRITE row 2 to quote the fairest baseline once measured; ADD one line "PS target: <10% of distance — we are at X% today, here is why" or move it to slide 4. **NEEDS WORK.**

**Slide 3 — Technical approach.** Strongest: readable native diagram in four stages. Weakest: PS components not visible; 364 words; "opt-in" chip. Missing: map-matching box, AI speed filter box, edge engine box, failure path. Unsupported: none. Technical: fine. **Fix:** VISUALIZE per §17; DELETE the italic plain-words lines on the input boxes; REWRITE chip 4 and 5. **NEEDS WORK.**

**Slide 4 — Feasibility.** Strongest: the log-scale chart and the "Still drifts" risk tile — the honesty is the best thing on the deck. Weakest: the chart has no PS-target line and no fair baseline; "1.7× closer" badge at 10 s is a loss against a frozen dot. Misunderstood: "it already works" vs. a 640 m error at one minute. **Fix:** ADD dashed 10% line and the freeze/constant-velocity bars; REWRITE the feasibility heading to "It runs, it is measured, and it is not yet at the target"; ADD a fifth risk pair: "Map-matching and AI speed filter not built → heading-only OSM (Fouque 2008), gated residual (Agastya ablation)". **NEEDS WORK.**

**Slide 5 — Impact.** Strongest: the 17-of-100 / 97-of-100 dot grid — instantly understood. Weakest: the app screenshot is dark, shows `ACQUIRING`, `-- KM/H`, no ring, no track — a judge sees an app doing nothing — and the caption's "48 satellites in view" is contradicted by the repo. Unsupported: two-wheeler photo and line; "safer navigation" (no safety metric). Excess: four benefit bullets are generic. **Fix:** REPLACE screenshot with blackout mode under a fix; REWRITE caption; DELETE "3 in 4 vehicles are two-wheelers" as a capability claim (keep as motivation if labelled); ADD ring radius in metres next to "97%" so the honesty is complete. **NEEDS WORK.**

**Slide 6 — References.** Strongest: the comparison matrix. Weakest: every ShadowNav cell is ✓ — a judge reads a self-serving table; missing the three prior-art citations the project's own docs mandate; "[repository link]" placeholder; PiDR unused. **Fix:** ADD row "Drift < 10% of distance (PS target)" with ✗ for ShadowNav and "next: 401 Hz re-run" beneath; ADD row "Map-matching (OSM)" with ✗ / planned; REPLACE PiDR with Fouque 2008 and add Gao & Groves, Barber 2023; fill the link; change "Two-wheeler capable ✓" to "target". **NEEDS WORK.**

No slide FAILS. No slide is a clean PASS except the title.

## 26. Visual audit

**Typography:** Times New Roman template titles, Arial body 11–14.5 pt; tiles at 11 pt sit on the floor the skill sets for laptop screening and below Reskilll's 14 pt advice (🟡). Hierarchy is consistent; italics on slide 3 overused. **Layout:** aligned, balanced, whitespace adequate on 2/4/5, crowded on 3. **Diagrams:** slide-3 flow is left-to-right with arrows and titled boxes; no decision points drawn; slide-4 chart is well labelled, log scale explained by the axis label, needs the target line. **Colour:** template navy/blue plus green (built) / orange (next) / magenta (DR) — semantic and consistent; the two-wheeler photo's warm palette fights the page. **Images:** three licensed photos with credits (good); the app screenshot is the one weak image and it is on the impact slide where it matters most. **Consistency:** footer, oval, page numbers correct on 2–6. Skill audit: **0 FAIL, 1 WARN (slide 3 words), 1 INFO (Team ID)**.

## 27. Idea-description field (the deliverable nobody drafted)

The portal asks for an idea description in addition to the PDF (guidelines p.17). Draft (≈150 words, 🔵):

> ShadowNav is a smartphone-only vehicle dead-reckoning engine for GNSS outages, built and validated on the IO-VNBD dataset the PS mandates. A kinematic EKF with a self-calibrating device-to-vehicle alignment, gyro-bias state, non-holonomic and Ackermann constraints and a stationary detector holds position from the accelerometer and gyroscope alone; a χ²/C/N₀ health gate drives an aided → degraded → dead-reckoning → re-acquiring state machine with a critically damped blend back to GNSS. A conformal-calibrated 90% radius replaces the filter's overconfident covariance (17% → 97% containment on held-out routes). Across 79 drives and 991 masked outages, median error is 180 m at 10 s and 1.5 km at 180 s — 1.7× to 43× better than unaided integration, but still above the PS's 10%-of-distance target because the dataset's GNSS updates only every ~9 s. The estimator is ported to a parity-tested Kotlin module inside a 2.2 MB Android 10+ app that samples at 401 Hz, where the same drives will be re-run; a gated learned speed filter and a heading-only OpenStreetMap constraint are the next two components.

## 28. Corrected scorecard (🔵, on the project's own published rubric from `research/SIH26168-external-review-response.md` §5)

| # | Axis | W | Ext-review "today" (Sep 5) | This audit (Sep 10) | Why |
|---|---|---|---|---|---|
| 1 | DR accuracy | 12 | 2 | 4 | measured, reproducible, but 8× off the PS target and unmeasured vs fair baselines |
| 2 | Blend-back | 10 | 3 | 4 | built and parity-tested; no metric |
| 3 | Drift/bias correction | 8 | 3 | 5 | gyro bias state, alignment, ZUPT measured |
| 4 | Detection latency | 5 | 3 | 3 | unmeasured |
| 5 | Urban-canyon NLOS | 6 | 4 | 4 | gate exists; no experiment |
| 6 | Covariance honesty | 6 | 5 | 8 | conformal coverage measured on route split |
| 7 | Novelty | 7 | 6 | 5 | algorithmic novelty thin; evaluation novelty real |
| 8 | Fusion design | 5 | 5 | 6 | — |
| 9 | Evaluation validity | 6 | 6 | 8 | fix-rate audit; missing fair baselines |
| 10 | Data | 5 | 8 | 9 | repairs with tests |
| 11 | Training feasibility | 4 | 6 | 6 | trained; weak gain |
| 12 | On-device latency | 5 | 3 | 3 | desktop proxy only |
| 13 | Compute/power | 5 | 2 | 3 | app runs; nothing measured |
| 14 | Cross-device | 4 | 2 | 2 | one phone |
| 15 | Two-wheeler | 3 | 1 | 1 | no data; claimed on deck |
| 16 | Reproducibility | 4 | 5 | 9 | seed, tests, golden vectors |
| 17 | IP/FTO | 3 | 8 | 8 | — |
| 18 | Licence | 2 | 7 | 9 | — |
| | **Weighted** | 100 | **4.1** | **5.2** | |

5.2/10 today; the on-device drive and two fair baselines would move axes 1, 2, 4, 12, 13 and are worth ~0.8. Hitting 10% on any real 50 m segment is worth more than everything else combined.

## 29. Prioritised action list

**Before 15 Sep (idea submission)**
1. Freeze-last-fix and constant-velocity baselines through `run_baseline.py`'s harness; add to `summarise_results.py`; redraw the slide-4 chart with both plus the 10% dashed line. *3 h.*
2. Print per-horizon calibrated ring radius (median metres) from `conformal_calibration.json` + the kinematic NEES/σ; put the 60 s value on slide 5. *1 h.*
3. Measure re-acquisition jump and detection latency on the 991 outages; one line on slide 3 or 4. *3 h.*
4. One outdoor drive on the moto g64 with a fix, hold-to-simulate-tunnel for ≥60 s twice, export CSV, replay through Python, report CRSE and drift %. Even one number at 401 Hz/1 Hz GNSS changes the story. *1 day incl. plumbing.*
5. Slide edits per §25; remove two-wheeler capability claims; add PS components and target; fix screenshot and caption; add three citations; fill repo link and Team ID. *3 h.*
6. Repo hygiene a judge will notice: `CLAUDE.md` status line ("no implementation started" is false); README links to a now-ignored `submission/`; decide whether the deck is tracked; `PLAN.md` results table is stale per `plans/…` FIX-1. *1 h.*
7. Paste the official PS text from the portal into `research/` and resolve the dossier's scenario discrepancy in writing. *30 min.*
8. Draft the idea-description field (§27). *30 min.*

**Before the finale (Dec 2026)**
9. Re-run the strapdown, accel-speed and centripetal ablations at 401 Hz from recorded drives — the project's own stated highest-value experiment.
10. Wire the speed net behind a confidence gate via ONNX Runtime; show the ablation including where it hurts.
11. Heading-only OSM constraint with Valhalla tiles for one Indian city; self-disable on zero candidates.
12. Real tunnel, real parking garage, one canyon drive — the PS's four scenarios, with the trip CSV as evidence.
13. Battery, thermal, latency over a 1 h drive on the moto g64.
14. Cut the Monaco tiles and de-emphasise the 3D orb in anything a judge sees.

## 30. Things this audit could not verify

- The official PS text on sih.gov.in (mirror used; fragments match).
- Whether the 15 Sep (guidelines) or 30 Sep (mirror) deadline governs — treat 15 Sep as binding.
- The "48 satellites in view" screenshot claim.
- PathPulse's 10% and Agastya's 1.4 m — competitor self-reports, metric definitions unknown.
- Any judging weights.
- Whether ISRO evaluators screen at idea stage or only at shortlisting.
