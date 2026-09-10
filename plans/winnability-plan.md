# ShadowNav — Winnability Plan (SIH 2026, PS SIH26168 / ISRO)

**Written:** 2026-09-10. **Answers:** [research/SIH26168-adversarial-validation.md](../research/SIH26168-adversarial-validation.md) (the audit). **Companion decisions:** [adr/ADR-001](adr/ADR-001-lead-with-evaluation-rigour.md), [adr/ADR-002](adr/ADR-002-osm-heading-then-gated-speed-cut-rendering.md), [adr/ADR-003](adr/ADR-003-publish-fair-baselines-and-ps-target.md).

**Numbers.** Every metric below was re-read today from `eval/results/*.json` and from `python/scripts/summarise_results.py` under the corrected scoring protocol (the estimator is no longer allowed to see the fix it is scored against — `test_the_scoring_instant_is_never_aided` in `python/tests/test_fair_baselines.py`). These supersede every figure in the audit (audit §0 quotes 146 % drift and 2.9–9.4 % of outages under target; both are pre-correction). The paired-comparison percentages are computed at run time by `summarise_results.py` from `kinematic.json` and the three `baseline_*.json` files; no stored file holds them yet (Track A item A12 fixes that). Anything not read from a file is marked **estimate**.

**Rules and dates** come from audit §2 (rules table, lines 47–64): nomination and idea submission close **15 Sep 2026** (guidelines PDF; a mirror shows 30 Sep — treat 15 Sep as binding), six-slide official template, PDF only, one idea-description text field, finale December 2026, ISRO may decline to award.

**Method used for this plan.** Failure modes were listed for the ISRO shortlisting and for the finale, the plan was designed against them, then it was read back three times — as an ISRO GNSS/INS scientist, as a previous SIH winner, and as a checker rejecting any number without a file. The objections that survived are folded in where they bite; the ones that changed the plan are: (i) the filter's cross-track error is *worse* than a straight line's, not just its along-track (kinematic.json vs baseline_cv.json `cte_median_m`), so "it is only speed" is not a complete story; (ii) coverage per horizon rests on 46–66 test outages, so ±0.05 is noise (conformal_calibration.json `n_test`); (iii) the 401 Hz argument is a hypothesis with research support, not a measurement, and must be labelled so until the drive is replayed; (iv) the human portal items are the most likely way to lose outright.

---

## 1. Two tracks

### Track A — before 15 Sep 2026 (hours)

Ordering is by what a judge sees first. Items marked **gate** block the submission. "In flight" items are being built by other agents today and are unverified; nothing on the deck may depend on them landing.

| # | Item | Owner | Hours | Output / evidence |
|---|---|---|---|---|
| A1 | **Portal, roster, SPOC** — see human list below | Human | 3 | Submission exists at all (**gate**) |
| A2 | Verify on sih.gov.in that the deadline is 15 Sep, not 30 Sep; paste the official PS text into `research/` (audit §30 could not verify either) | Human | 0.5 | `research/SIH26168-PS-official-text.md` (new, text only) |
| A3 | Deck: delete "No jump on the map"; replace with the measured line "largest displayed step after re-acquisition: median 184–215 m on 9 s-GPS data (kinematic.json `reacq_max_step_median_m`); target on the phone at 1 Hz GPS: below the ring" | Claude (deck agent) | 0.5 | `submission/ShadowNav_SIH2026_Idea.pptx` |
| A4 | Deck: replace "97 %" with "96 % of true positions inside the ring on held-out routes (nominal 90 %), ring 0.85 km at 10 s, 3.8 km at 60 s" (conformal_calibration.json `mean_coverage_calibrated` = 0.961; kinematic.json `radius90_cal_median_m`) | Claude (deck agent) | 0.5 | deck slide 5 |
| A5 | Deck slide 4: redraw the chart with the two fair baselines (freeze, straight line) beside the MVP and the naive floor, and a dashed PS 10 % line; caption states that a straight line at last GNSS speed matches or beats the filter at every horizon on this dataset | Claude (deck agent) | 2 | deck slide 4; source `eval/results/baseline_freeze.json`, `baseline_cv.json`, `kinematic.json` |
| A6 | Deck: remove the "1.7×–43×" headline and every two-wheeler *capability* claim (slides 2, 5, matrix); keep two-wheelers only as a stated target with "no two-wheeler data yet" | Claude (deck agent) | 1 | deck slides 2, 5, 6 |
| A7 | Deck slide 3: show the PS's five component names as boxes; Map-Matching (heading-only OSM, Fouque 2008) and AI Speed Filter (gated residual) labelled by their true status on the day (see §3); edge engine (`shadownav-core`, parity 1e-9) as its own box | Claude (deck agent) | 1.5 | deck slide 3 |
| A8 | Deck slide 6: matrix rows "Drift < 10 % of distance (PS target)" with ✗ for ShadowNav and "Map-matching (OSM)" with its true status; add Fouque 2008, Gao & Groves, Barber 2023; drop PiDR; fill repository link and Team ID | Claude (deck agent) + Human (Team ID, link) | 1 | deck slide 6 |
| A9 | Idea-description field: rewrite audit §27's draft with today's numbers (194 m at 10 s, 1.48 km at 180 s, 96 %, "does not yet beat a straight line on 9 s-GPS data") | Claude | 0.5 | `submission/IDEA_DESCRIPTION.md` (paste-ready, ≤ 200 words) |
| A10 | Repo hygiene a judge will see: `README.md` results table still shows pre-correction values (180/368/640/1071/1474 m and 17 % → 97 %; README.md lines 39–54) — update to 194/378/658/1086/1480 and 14 % → 96 %; fix `CLAUDE.md` "no implementation started"; README's `submission/` link points at a gitignored directory | Claude | 1 | `README.md`, `CLAUDE.md` |
| A11 | Add the persisted summary: make `summarise_results.py` also write `eval/results/summary.md` so the paired-win percentages have a file | Claude | 0.5 | `eval/results/summary.md` |
| A12 | Outdoor drive on the moto g64 5G — specification below | Human | 3 (incl. travel) | trip CSVs + notes + screenshot (see below) |
| A13 | Trip-CSV replay path from the phone into the offline pipeline (**in flight**, previous attempt produced nothing) — required before A12's files can be scored | Claude | 4–8 | `python/scripts/replay_trip.py` (name **estimate**) → `eval/results/device_drive_*.json` |
| A14 | If A12 and A13 both land by 14 Sep: score the drive at 401 Hz IMU / 1 Hz GNSS and put the single number on slide 4 labelled "one drive, n = k blackouts" | Claude | 2 | `eval/results/device_drive_*.json` |
| A15 | Heading-only OSM constraint with/without ablation on the test fold (**in flight**; 33 MB Overpass data for four routes already under `data/osm/`) — deck may say "built, ablation: X" only if the result file exists | Claude (map agent) | 4–8 | `eval/results/kinematic_maphead.json`, `kinematic_maphead_off.json` (names from `run_map_ablation.py`) |
| A16 | Confidence-gated learned speed filter + ONNX export (**in flight**, relaunched). If it does not land with an ablation file by 14 Sep the deck says "next", not "built" | Claude | 8–16 | `eval/results/kinematic_speednet_gated.json` (name **estimate**) |
| A17 | Export PDF, open it on a machine without the fonts, count six slides, check pointers unchanged (audit §24) | Human | 0.5 | `submission/ShadowNav_SIH2026_Idea.pdf` |
| A18 | Re-run `pytest` and `./gradlew :shadownav-core:test`; record the counts that the deck quotes (README says 161 Python tests; today's changes may have moved it) | Claude | 0.5 | terminal output pasted into `eval/results/summary.md` |

Claude total: ~28–43 h across agents; the deck items (A3–A9) are ~7.5 h and are the only ones the submission cannot go without. Human total: ~7.5 h.

**Human-only items and exactly what to hand back**

1. **Team roster and eligibility** (audit §2, lines 49–51): six students including the leader, at least one female member, all from one college, all selected in the college's internal hackathon. Hand back: a text file `submission/TEAM.md` with names, roll numbers, branch, year, gender, e-mail, phone, and who is leader; team name "ShadowNav" (must not contain the institute name). Team details cannot be changed after entry.
2. **SPOC nomination and college letter**: confirm with the SPOC that the team is nominated on the portal for SIH26168 and obtain whatever letter or ID the college issues. Hand back: the Team ID string the portal generates (goes on slide 1 and slide 6), and a PDF scan of the letter if one exists.
3. **Portal fields** (audit §2, line 54): problem-statement ID `SIH26168`, idea title "ShadowNav — smartphone-only dead reckoning through GNSS outages" (or the deck title verbatim), the idea-description text (paste from `submission/IDEA_DESCRIPTION.md`), the six-slide PDF. Submit at least two days early; the PS freezes at 500 ideas (audit §2, line 52). Hand back: a screenshot of the confirmation page.
4. **The outdoor drive** (moto g64 5G, app foreground, phone in a rigid cradle, screen on, battery ≥ 50 %):
   - Start recording while parked with a fix and wait until the app leaves `ACQUIRING`.
   - Drive at least 5 min with several turns *before* the first blackout so alignment can lock (alignment comes from turns; `python/README.md` "Device-to-car alignment is a prerequisite").
   - Then hold **Simulate tunnel** for at least **60 s three times** and **180 s once**, on ordinary roads, at least one hold spanning a turn and one on a straight; release, drive ≥ 30 s aided between holds.
   - **Minimum drive: 30 min; preferred: two drives on different days.** A real tunnel or car park is welcome but the button is what makes the run scorable (the app has no truth without GPS).
   - Hand back, unrenamed, exactly as the app shares them: the **trip CSV files** (26 columns, `android/README.md` "Trip recording"); one **screen recording (mp4)** of a full hold-release cycle; one **screenshot (PNG)** in blackout mode with a fix and the ring visible (replaces the `ACQUIRING` screenshot the audit flags in §25); and a **notes file `drive_notes.md`** with date, time, vehicle make, where the phone was mounted, road type, wall-clock time of each hold and its duration, battery % at start and end, whether `[RATE DEGRADED]` ever appeared, the IMU rate the diagnostics panel showed, and the satellites-in-fix count the panel showed outdoors (this is the only way to support or retire the "48 satellites" caption, audit §3).
5. **Mentor**: identify one GNSS/INS mentor (≥ 5 years' experience) to name after shortlisting (audit §2, line 59). Hand back: name and affiliation.

### Track B — before the December 2026 finale (weeks; week 0 = 15 Sep)

| # | Weeks | Item | Owner | Evidence |
|---|---|---|---|---|
| B1 | 0–2 | Replay every drive CSV through the pipeline at the phone's real rates; report CRSE, drift %, cross-track, max step, ring radius at 10/30/60/120/180 s. This is the decisive experiment (android/README.md "The number that matters") | Claude | `eval/results/device_drive_*.json` |
| B2 | 1–3 | **Residual ~200 m re-acquisition step.** Measured median largest displayed step is 184–215 m at every horizon while the snap it replaces grows 272 → 1504 m (kinematic.json). A step that does not scale with the snap is not the blend. Suspects, in order: (a) the ordinary position update at the *second* fix after re-anchor — the filter re-anchors at fix k0, then dead-reckons ~9 s on held speed, and the k1 update absorbs a 10 s-class error (~194 m median, kinematic.json 10 s CRSE), bypassing the display blend; (b) the gate-escape re-anchor in `filter/kinematic.py` (`max_consecutive_rejections = 3`), which calls `reanchor` without arming the blend; (c) the blend's own peak velocity (ω = 2.3 rad/s, `filter/fsm.py`). Diagnostic: log per-sample step, time since k0 and the event that coincides; fix so every filter jump routes through the display residual; re-measure. On the phone the same mechanism operates at 1 Hz GPS, so the expected step is ~10× smaller — measure it there too | Claude | `eval/results/kinematic.json` (re-run), `device_drive_*.json` |
| B3 | 1–4 | **Heading ablation.** The MVP's cross-track error (18.6/75.5/173.7/377.7/473.6 m) is worse than a straight line's (6.4/44.0/136.1/326.0/361.3 m) and worse than raw gyro heading hold (10.7/53.4/139.9/354.5/387.9 m) at every horizon (kinematic.json, baseline_cv.json, baseline_gyro.json `cte_median_m`). Something in the bias state, NHC, Ackermann bound or alignment makes heading worse than doing less. Ablate each on the full 79-sequence set; ship the best | Claude | `eval/results/kinematic_no_*.json` (re-run on 79 seq) |
| B4 | 2–5 | Re-run the three 10 Hz negatives at 401 Hz on drive data: 21-state strapdown, accelerometer-derived speed, centripetal speed `v = a_y/ω_z` (open-track F.1). Each is a go/no-go with a number, not an assumption | Claude | `eval/results/device_ablation_*.json` (name **estimate**) |
| B5 | 2–6 | Gated learned speed filter on device: ONNX Runtime Mobile, INT8/XNNPACK; ablation on the test fold showing where it helps (30–120 s) and where it hurts (180 s) (python/README.md "Does it help the filter?"); on-device latency measured | Claude | `eval/results/kinematic_speednet_gated.json`, `inference_latency_device.json` (**estimate**) |
| B6 | 3–7 | Heading-only OSM constraint on device: pre-fetched extract for one Indian city (Valhalla tiles or the Overpass cache format already in `data/osm/`); self-disable on zero candidates within 200 m (Newson & Krumm rule) and inside car parks | Claude | `eval/results/kinematic_maphead*.json`, device replay |
| B7 | 4–9 | **Scenario drives** — human: one real tunnel, one multi-level car park, one forested highway, one dense urban street; each with the tunnel button held before entry so truth exists on both sides, CSVs and notes as in Track A | Human | `data/drives/*.csv` (**estimate** path) + `eval/results/device_drive_*.json` |
| B8 | 6–9 | Battery, thermal and per-sample latency over a 1 h drive on the moto g64 | Claude + Human | `eval/results/device_power.json` (**estimate**) |
| B9 | 8–11 | Re-fit conformal factors on drive data; publish ring radius in metres per horizon; report `n_test` beside every coverage figure | Claude | `eval/results/conformal_calibration.json`, `shared/conformal.json` |
| B10 | 9–12 | Finale demo: replay-first (committed data, web MVP), phone second (desk with a fix, hold the button); two rehearsals; pre-recorded fallbacks for every live step (audit §22) | Claude + Human | `submission/DEMO_RUNBOOK.md` |
| B11 | 0–12 | Kill list (§4) enforced: no time on rendering, Monaco tiles, web polish, Mamba/MoE, AGC, two-wheeler claims | Both | — |
| B12 | 0–2 | Mentor confirmed; travel and hardware list for the nodal centre | Human | — |

Human-only in Track B: B7 scenario drives (hand back: CSVs, notes, one photo of the phone mount, the mp4 of the tunnel entry), the mentor, and finale logistics.

---

## 2. Narrow novelty statement and banned claims

**The statement the deck carries (38 words):**

> We measured the mandated dataset before trusting it, our own overconfidence before drawing a circle, and our filter against a straight line before claiming a gain. Evaluation rigour, calibrated coverage, a parity-tested phone port, and published negative results.

What it rests on, with the file that proves each part:

- **Evaluation rigour.** GPS in IO-VNBD updates every 9.0 s (median), not 1 Hz — 14,067 real fixes in 1.07 M rows (`python/README.md` "GPS updates every ~9 s, not 1 Hz"; `eval/results/gps_rate_audit.json`); Excel date corruption in 12 of 72 files, selective toward low-satellite rows, repaired invertibly with regression tests (`python/README.md` "Excel date corruption"; `python/tests/test_repair.py`); and today's scoring-protocol correction — the scored instant is now unconditionally unaided (`python/tests/test_fair_baselines.py::test_the_scoring_instant_is_never_aided`).
- **Calibrated coverage.** Raw 90 % ellipses contain 14 % of errors on held-out routes; one scalar per horizon fitted on val brings test containment to 96 % (`eval/results/conformal_calibration.json`). Stated as *empirically calibrated coverage on held-out routes*, never guaranteed.
- **Parity-tested port.** `shadownav-core` reproduces the Python estimator to 1e-9 on nine golden cases (`android/shadownav-core/src/test/kotlin/com/shadownav/core/ParityTest.kt`; `android/README.md` "Why shadownav-core has no Android dependency"); 2.2 MB release APK, minSdk 29.
- **Honest negative results.** "Our filter does not beat a straight line on 10 Hz data, and we measured it": straight line at last GNSS speed 182/346/612/979/1326 m vs ShadowNav 194/378/658/1086/1480 m at 10/30/60/120/180 s (`baseline_cv.json`, `kinematic.json`); the speed net's +1.08 m/s test bias with opposite sign on val (`eval/results/speednet_training.json`; `python/README.md`); accelerometer speed and centripetal speed hurt at 10 Hz (`eval/results/kinematic_no_accel.json`, `kinematic_no_cent.json`).

**The three citations that pre-empt a judge** (audit §12; open-track Track C, D):

1. Fouque, Bonnifait & Bétaille, *map-aided odometry with road bearing as a heading observation*, IEEE/ION PLANS 2008 — the heading-only map constraint is prior art; we implement it, we do not claim it.
2. Gao & Groves, *context-adaptive navigation* (UCL) — satellite count and C/N₀ as an environment context; our χ² gate and de-weighting follow it.
3. Barber, Candès, Ramdas & Tibshirani, *Conformal prediction beyond exchangeability*, Ann. Stat. 2023 (arXiv:2202.13415) — why our coverage claim is empirical, not guaranteed.

**Banned claims, verbatim from `research/SIH26168-external-review-response.md` §9 (lines 309–325):**

1. ~~"We estimate sensor bias and mounting alignment online"~~ — AVNet already does.
2. ~~"Tightly-coupled map constraints are novel"~~ — Fouque 2008.
3. ~~"Context-adaptive switching is novel"~~ — Gao & Groves.
4. ~~"Statistically guaranteed confidence"~~ — exchangeability fails on trajectories. Say *"empirically calibrated coverage — 90 % containment on held-out routes."*
5. ~~"Our blackout/blend FSM is novel"~~ — `algoarchemist/seamless-navigation` shipped a four-mode hysteresis FSM with dwell timers first. Claim the *fiducial re-anchor* and the *degraded-but-present* path instead.
6. ~~"AGC-based jamming detection works on our target device"~~ — unverified, API 33, and possibly silent in a tunnel.

**Newly banned by this plan:**

7. ~~"1.7×–43× better than plain sensor maths"~~ as a standalone headline — the comparator is unaided double integration, which nobody ships; against a straight line the ratio is 0.80–1.00× (`summarise_results.py` paired table). The naive floor may appear only as the bottom bar of a chart that also shows freeze and straight-line.
8. ~~"No jump on the map"~~ — the measured median largest displayed step after re-acquisition is 184–215 m (`kinematic.json` `reacq_max_step_median_m`). Say "blended, not snapped; residual step measured and being removed (Track B2)".

Also removed, per audit §3 (class E): every two-wheeler *capability* claim (see §4).

---

## 3. PS-coverage table

Status vocabulary: **built + measured** (result file exists) · **built, unmeasured** · **in flight** (being built today, no file) · **planned** · **absent**. "At submission" assumes only the deck items A3–A10 land; in-flight items are shown as the *worse* of their two possible states because the deck must not depend on them. Evidence paths marked **estimate** do not exist yet.

| PS requirement (audit §5, lines 100–104) | Today (10 Sep) | At submission (15 Sep) | At finale (Dec) | Evidence file | Owner |
|---|---|---|---|---|---|
| Calibration Engine (phone-to-vehicle orientation, automatic) | built + measured offline: alignment from GNSS-accel correlation, quality score, works in ~84 % of runs; stationary detector verified on device | same; deck says "implemented, following Wahlström 2015 / AVNet" | measured on drive data; alignment lock time reported | `python/shadownav/filter/alignment.py`; `python/README.md` "Device-to-car alignment"; `android/README.md` "A fourth bug" | Claude |
| AI Speed Filter, running locally (deep-learning *or* statistical) | trained, opt-in, off by default, not on device; helps 9–13 % at 30–120 s, hurts 19 % at 180 s on 8 sequences | **in flight** → deck says "gated residual — next" unless `kinematic_speednet_gated.json` exists | gated, on device via ONNX Runtime, ablation published incl. where it hurts; plus turn-based speed at 401 Hz as the statistical path | `eval/results/kinematic_speednet.json`, `speednet_training.json`; `kinematic_speednet_gated.json` (**estimate**) | Claude |
| Map-Matching Framework (offline OSM + kinematic constraints) | **in flight**: `python/shadownav/map/` (heading_constraint, index, osm), Overpass data for 4 routes in `data/osm/`, ablation script written; no result file at time of writing | deck says "heading-only OSM constraint (Fouque 2008), built; ablation: [number]" only if `kinematic_maphead*.json` exists, else "built, unmeasured" | on device with an Indian-city extract; self-disable on no candidate; car-park dead zone stated | `eval/results/kinematic_maphead.json`, `kinematic_maphead_off.json` (from `run_map_ablation.py`) | Claude (map agent) |
| GNSS + INS Fusion | built + measured: 5-state kinematic EKF, position/speed/course updates, χ² gate, gate escape after 3 rejections | same | same, plus heading ablation result (B3) | `eval/results/kinematic.json`; `python/tests/test_kinematic_fsm.py` | Claude |
| Seamless Transition (instant switching both ways) | built + measured: detection latency 1.00 s (FSM dwell, not adaptive); blend reaches the display after today's fix; residual max step 184–215 m median | deck states both numbers honestly; "no jump" removed | max step below the ring at 1 Hz GPS (target ≤ 20 m, **estimate**); latency measured on the phone | `eval/results/kinematic.json` (`detection_latency_median_s`, `reacq_max_step_median_m`) | Claude |
| Drift < 10 % of distance travelled (PS target) | **not met**: median 155/103/88/84/80 %; share of outages under 10 %: 0.0/0.0/0.5/0.0/3.1 % | deck shows the ✗, the number, and the reason (9 s GPS, 10 Hz IMU) | first measurement at 401 Hz / 1 Hz on real drives; target: < 10 % on at least one ≥ 60 s blackout per scenario | `eval/results/kinematic.json` (`drift_median_pct`, `share_under_10pct`); `device_drive_*.json` (**estimate**) | Claude + Human |
| ≥ 10 Hz position update on the phone | built, unmeasured: filter runs per IMU sample at 401 Hz; output latency never measured | same, stated as such | measured ms/sample on the moto g64 | `android/README.md` "On-device results" (401 Hz); `device_power.json` (**estimate**) | Claude |
| ~200 Hz edge-deployable engine | built, unmeasured: `shadownav-core` is a pure-JVM module with no Android dependency; no throughput benchmark (a JVM benchmark brief died today) | "exists, parity 1e-9; throughput next" | JVM throughput benchmark ≥ 200 Hz on a laptop and on the phone | `ParityTest.kt`; `eval/results/jvm_throughput.json` (**estimate**) | Claude |
| IO-VNBD used for training and validation | built + measured: 79 sessions, 991 outages, route-level split, four defects repaired | same, and it is the innovation story | same, plus device data as a second dataset | `eval/splits/shadownav_s_split.yaml`; `python/README.md` "Findings that changed the plan" | Claude |
| Working mobile app | built, partially verified: captures at 401 Hz, foreground service, stationary hold verified; everything after the first fix untested on hardware | one outdoor drive (A12) turns "untested" into "one drive, k blackouts" | scenario drives; battery/thermal | `android/README.md` "Not yet measured"; `device_drive_*.json` (**estimate**) | Human (drive) + Claude |
| Edge-deployable software engine | as "~200 Hz engine" row | same | same | same | Claude |
| Scenario: tunnel / underpass | synthetic masking only (tunnel-like) | same, labelled "synthetic outage on real drives" | one real tunnel drive with button held before entry | `kinematic.json`; B7 CSVs | Human + Claude |
| Scenario: multi-level parking | absent; and OSM has no roads inside car parks (open-track Track C) so the map constraint must self-disable | stated as a known gap | one car-park drive; map self-disable shown | B7 CSVs | Human + Claude |
| Scenario: dense forested highway | absent; correct tool is the χ² gate + C/N₀ de-weighting (degraded, not lost) | stated as design only, citing Gao & Groves | one forested-road drive; gate statistics reported | `kinematic.json` gate stats via diagnostics (not summarised today) | Human + Claude |
| Scenario: deep urban canyon | absent as an experiment; gate exists; IO-VNBD has no per-satellite C/N₀ | stated as design only | one dense-urban drive; count of rejected fixes reported | B7 CSVs | Human + Claude |

---

## 4. Kill list

1. **Filament 3D status orb and bloom pipeline** (`plans/shadownav-3d-mvp-web-deck.md` steps 1–2; `RenderTier`, `GpuBenchmark`, `orb.filamat`): a third of the app's Kotlin serves rendering the PS never asks for on a project whose selling point is a low-end phone — leave the code, spend zero further hours, and keep it out of every slide and the APK-size story.
2. **Bundled Monaco map tiles and demo path**: a Monaco basemap in an ISRO room is a self-inflicted question; replace with an Indian extent when the OSM work needs one, otherwise hide the map in the demo.
3. **Further web-MVP polish** (`frontend/`): it stays as a replay surface for the demo exactly as it is; no new features, no deployment work.
4. **Mamba / MoE / 21-state strapdown on 10 Hz data**: the strapdown diverged to 5×10⁴ m/s at 10 Hz (`python/README.md` "Two filters, and why"), Mamba is a gated RNN at this sequence length (open-track F.3), and the MoE router needs 401 Hz features — none of the three gets a line of work until B4 produces high-rate results.
5. **AGC and interference attribution on roads**: AGC goes silent exactly inside a tunnel and India's documented interference is aviation, not roads (open-track Track A; PLAN.md §6 item 1) — keep the three-state readout in the app, never put it on a slide.
6. **Every two-wheeler capability claim**: there are zero two-wheeler samples anywhere in the project (audit §3, class E); two-wheelers may appear only as a stated target with "no data yet".
7. **The "× better than plain maths" framing**: the naive floor is a strawman nobody ships; the straight-line and freeze baselines are the comparators, and the floor appears only as the bottom bar of a chart that shows them too.

---

## 5. Risk register (top 8)

| # | Risk | Trigger | Mitigation | Demo-day fallback |
|---|---|---|---|---|
| R1 | **The filter loses to constant velocity on the mandated dataset and a judge finds it.** Straight line 182/346/612/979/1326 m vs MVP 194/378/658/1086/1480 m; paired, the MVP wins only 49/36/34/29/27 % of outages (`baseline_cv.json`, `kinematic.json`, `summarise_results.py`) | Any judge asks "versus extrapolating the last velocity?" or opens the repo | We say it first, on slide 4, with the cause: speed is held from a fix up to 9 s stale and the 10 Hz IMU cannot observe speed; heading integration adds error rather than removing it on these mostly straight windows (B3). Then the fix and its date: 401 Hz / 1 Hz on the phone (B1), turn-based speed (B4), gated residual (B5), map heading (B6) | "Here is the paired table; here is why; here is the device number if A14 landed, otherwise the drive CSV that will produce it" |
| R2 | **Nothing meets the PS's 10 % target.** 0.0/0.0/0.5/0.0/3.1 % of outages (`kinematic.json` `share_under_10pct`); median drift 80–155 % | The evaluator wrote the target and checks it first | Put the ✗ and the number on the matrix ourselves (ADR-003); explain that at a 9 s fix period even the *frozen dot* has 93–194 % drift (`baseline_freeze.json`), so the target is unreachable on this dataset by any method that does not observe speed; state what would meet it and when it will be measured (B1, B7) | Show the frozen-dot and straight-line drift beside ours so the judge sees the dataset's floor, not just our miss; if a device number exists, show it labelled n = k |
| R3 | **The residual ~200 m re-acquisition step.** Median largest displayed step 184–215 m after the blend fix (`kinematic.json` `reacq_max_step_median_m`); the deck used to say "no jump" | A judge asks for the step in metres; or the phone visibly hops on the desk demo | Remove the claim (A3); diagnose and fix the source (B2: second-fix update, gate-escape re-anchor, or blend velocity); measure on the phone at 1 Hz where the expected step is ~10× smaller (**estimate**) | Show the snap-vs-step table (272 → 184 m at 10 s): "we halved it and measured the rest"; demo replay rather than the live phone |
| R4 | **No outdoor drive before 15 Sep.** Everything after the first fix is untested on hardware (`android/README.md` "Not yet measured") | Human time, weather, or the replay path (A13) not landing | Drive spec in §1 needs 30 min; the CSV is scorable later even if A13 slips, so the drive should happen regardless; the screenshot alone fixes the audit's slide-5 problem | Deck says "recorded, replay in progress" only if the CSV exists; otherwise "untested on hardware past the first fix" stays on the risk tile — never a claimed device number |
| R5 | **The ring is kilometres wide.** Calibrated 90 % radius 848 m / 1.5 km / 3.8 km / 9.2 km / 13.7 km (`kinematic.json` `radius90_cal_median_m`); coverage per horizon 1.00/0.83/1.00/0.98/1.00 on n_test 66/63/57/49/46 (`conformal_calibration.json`) | "What does a driver do with a 4 km circle?" | Frame it as "never lies small": the raw ring (39 m at 10 s) contained 1.5 % of truths; the honest ring is large because the error is large, and it will shrink exactly as fast as the error does; report n_test beside every coverage number; refit on drive data (B9) | Show raw-vs-calibrated coverage (0.14 → 0.96) as the point, and say the radius aloud before being asked |
| R6 | **Portal or PowerPoint mishaps.** Wrong deadline (15 vs 30 Sep), roster ineligible, PS frozen at 500 ideas, seven slides, template pointers edited, PDF fonts substituted, blank idea-description field | Any of A1, A2, A17 skipped | A1/A2 done first; submit ≥ 2 days early; A17 opens the PDF on a second machine; idea description drafted (A9) | If the PPTX is locked on the day, present the PDF (audit §22); keep the PDF and description text in two places |
| R7 | **A judge cites PathPulse's 10 % drift or Agastya's 1.4 m ATE.** Both are self-reports with unknown metric definitions (audit §30; dossier §10) | Judge has read the public repos | Do not dispute their numbers; state ours with their definitions attached (CRSE at the first real fix after the outage, on 991 outages, seed and split published) and offer the harness: "run any method through `run_baseline.py` on the same split"; note Agastya's own ablation shows ungated ML is worse than classical, which is the gating design we adopt | Hand the judge the one-page metric definition; if they want a number in their metric, say we will compute ATE on the same windows when the definition is known |
| R8 | **The 401 Hz hypothesis fails on the drive.** Higher-rate IMU may not make speed observable at constant-speed cruising either (the dossier's own caveat, §14: SJTU found IMU fusion in tunnels "insufficient for long-term reliability") | B1/B4 return no improvement | The claim is stated as a hypothesis with research support (CarSpeedNet 1.8 m/s RMSE from phone accelerometer, open-track F.2), never as a result; the map heading constraint (B6) and turn-based speed at entries/exits do not depend on it; the negative result itself is publishable and consistent with the pitch | Present the finale as "measured at both rates; here is where the physics stops", with the map and gated components carrying the improvement |

---

## 6. Success metrics per track

| Track | Metric | Threshold | Proof file |
|---|---|---|---|
| A | Submission accepted on the portal with Team ID, six-slide PDF, idea description | done by 13 Sep | portal confirmation screenshot; `submission/ShadowNav_SIH2026_Idea.pdf` |
| A | Deck contains no banned claim (§2, items 1–8) and no two-wheeler capability claim | zero occurrences (grep the PPTX text) | `submission/ShadowNav_SIH2026_Idea.pptx` |
| A | Deck shows freeze, straight line, MVP and the 10 % line on one chart | present | deck slide 4; `eval/results/baseline_freeze.json`, `baseline_cv.json`, `kinematic.json` |
| A | Deck states coverage 96 % with radius in metres and the residual step in metres | present | deck slide 5; `conformal_calibration.json`; `kinematic.json` |
| A | PS component names visible on slide 3 with true status | five boxes | deck slide 3 |
| A | README/CLAUDE.md consistent with the result files | README table = 194/378/658/1086/1480 m | `README.md`; `eval/results/kinematic.json` |
| A | One outdoor drive recorded | ≥ 30 min, ≥ 3 holds ≥ 60 s, 1 hold ≥ 180 s | trip CSVs + `drive_notes.md` |
| A (conditional) | Map-heading ablation on the test fold | file exists; paired CTE change reported (any sign) | `eval/results/kinematic_maphead.json`, `kinematic_maphead_off.json` |
| B | Device drive scored at 401 Hz / 1 Hz | CRSE and drift % at 10/30/60/120/180 s on ≥ 10 blackouts | `eval/results/device_drive_*.json` |
| B | PS target on device | drift < 10 % on ≥ 1 blackout ≥ 60 s in each of tunnel and car park (**estimate** of what is achievable; the honest fallback is reporting the share) | `device_drive_*.json` `share_under_10pct` |
| B | Filter beats straight line on device | paired win share > 50 % at every horizon | `device_drive_*.json` vs a device `baseline_cv` run |
| B | Residual step | median `reacq_max_step_m` < median `radius90_cal_m` at 10 s on IO-VNBD, and < 20 m on device (**estimate**) | `kinematic.json`; `device_drive_*.json` |
| B | Heading | MVP `cte_median_m` ≤ `baseline_gyro.json` at every horizon after B3 | `kinematic.json`, `baseline_gyro.json` |
| B | Coverage | calibrated coverage within 0.85–0.95 at every horizon, n_test reported | `conformal_calibration.json` |
| B | Gated speed filter | on-device p95 latency < 30 ms; ablation shows no horizon worse than control by > 5 % | `inference_latency_device.json`, `kinematic_speednet_gated.json` (**estimate** names) |
| B | Map constraint on device | self-disables inside the car-park drive; reduces CTE on the tunnel drive | `device_drive_*.json` with/without |
| B | Power | battery %/h and ms/sample over 1 h | `device_power.json` (**estimate**) |
| B | Edge engine | JVM throughput ≥ 200 Hz | `jvm_throughput.json` (**estimate**) |
| B | Demo | two full rehearsals with fallbacks exercised | `submission/DEMO_RUNBOOK.md` |

---

## 7. What we say to ISRO

We built what you asked for and measured it more carefully than it flatters us. On the mandated IO-VNBD data (79 drives, 991 GNSS cuts, published split, seeded) our phone-only estimator is 194 m off after 10 s and 1.5 km after 180 s. That is 80–155% of distance travelled against your 10% target; essentially none of our outages meet it. A straight line at the last GNSS speed, with no inertial sensor at all, does as well or slightly better at every horizon. We know because we ran that baseline ourselves.

The reason is the dataset, and we can show it: IO-VNBD's IMU logs at 10 Hz and its GPS updates every 9 s, so the speed we hold into an outage is already up to 9 s stale, and the vibration and turn signals that would observe speed are aliased away. Speed is unobservable there; even a frozen dot drifts 93–194%. Our audit of that dataset (the fix rate, the Excel-corrupted satellite column) is part of the submission.

What changes it is the phone: 401 Hz IMU and 1 Hz GNSS, measured on a ₹10k Android. On that data we will re-run turn-based speed, a confidence-gated learned residual and a heading-only OpenStreetMap constraint, each as an ablation with a number. Our confidence ring is calibrated (96% containment on held-out routes, radius stated in metres), so when we are wrong the app says so. We would rather show the gap and the plan than a number we cannot reproduce.

(≤ 250 words)
