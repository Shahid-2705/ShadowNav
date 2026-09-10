# ADR-001: Lead the pitch with evaluation rigour, calibrated coverage and honest negatives, not algorithmic novelty

## Context

The SIH 2026 evaluation criteria list "novelty of the idea" first (audit §2, line 56). The project's algorithmic core — a 5-state kinematic EKF with a gyro-bias state, non-holonomic and Ackermann constraints, a χ² gate, a four-state FSM and a critically damped blend — is textbook (Groves; Fouque 2008; Gao & Groves) and a domestic competitor shipped a functionally equivalent FSM first (`algoarchemist/seamless-navigation`, dossier §10; external-review §9 item 5). Four novelty claims were already killed in `research/SIH26168-open-track-findings.md` §0 and two more in `research/SIH26168-external-review-response.md` §9. The audit's novelty verdict (§9) is that algorithmic novelty is "not sufficiently defensible" while experimental and evaluation novelty "is defensible".

What the project actually has that the domestic field does not, each with a file:

- The IO-VNBD fix-rate audit: GPS every 9.0 s median, 14,067 real fixes in 1.07 M rows, which invalidates naive 10 Hz scoring (`python/README.md` "GPS updates every ~9 s, not 1 Hz"; `eval/results/gps_rate_audit.json`).
- The Excel-corruption repair: 12 of 72 files, selective toward low-satellite rows, inverted with regression tests (`python/README.md`; `python/tests/test_repair.py`).
- The scoring-protocol correction made today: the estimator is scored at an instant it was never aided at (`python/tests/test_fair_baselines.py::test_the_scoring_instant_is_never_aided`). The correction made our own numbers slightly worse, which is the point.
- Calibrated coverage: raw 90 % ellipses contain 14 % of errors; one scalar per horizon fitted on val gives 96 % on test (`eval/results/conformal_calibration.json`).
- A parity-tested Kotlin port, 1e-9 on nine golden cases, 2.2 MB APK, minSdk 29 (`android/shadownav-core/.../ParityTest.kt`; `android/README.md`).
- Negative results, measured and published: the filter does not beat a straight line at last GNSS speed on 10 Hz data (`eval/results/baseline_cv.json` 182/346/612/979/1326 m vs `kinematic.json` 194/378/658/1086/1480 m); the speed net carries a +1.08 m/s test bias of opposite sign on val (`eval/results/speednet_training.json`); accelerometer and centripetal speed hurt at 10 Hz (`kinematic_no_accel.json`, `kinematic_no_cent.json`).

Any pitch that leads with the algorithm invites the one question the project cannot answer well — "what does your filter do that AVNet, Fouque or Gao & Groves did not?" — and hides the material a domain scientist would respect.

## Decision

The deck, the idea-description field and the finale talk lead with a 38-word novelty statement about measurement, not the filter:

> We measured the mandated dataset before trusting it, our own overconfidence before drawing a circle, and our filter against a straight line before claiming a gain. Evaluation rigour, calibrated coverage, a parity-tested phone port, and published negative results.

The algorithm is described as "implemented, following" its sources (AVNet / Wahlström 2015 for alignment, Fouque 2008 for the map heading, Gao & Groves for the gate, Barber 2023 for why coverage is empirical). The three citations appear on slide 6 before a judge supplies them. The eight banned claims in `plans/winnability-plan.md` §2 are enforced by a text grep of the PPTX before export.

## Alternatives considered

1. **Lead with the algorithm and the "1.7×–43× better" headline.** Rejected: the comparator is unaided double integration, which nobody ships; against the straight-line baseline the ratio is 0.80–1.00× (`summarise_results.py` paired table). A judge who runs the obvious baseline finds this in minutes.
2. **Lead with the NavIC framing** (dossier §12a: NavIC at three satellites, its fallback assumes another constellation is reachable, which fails in the PS's scenarios). Kept as the *problem* hook on slide 2, but it is a framing, not a contribution; it cannot carry the novelty criterion on its own.
3. **Lead with the two-wheeler market gap** (PLAN.md §1, §3 item 7). Rejected for the deck: zero two-wheeler samples exist anywhere in the project (audit §3, class E). Allowed only as a stated target.
4. **Lead with the planned components** (heading-only OSM constraint, gated speed residual) as if built. Rejected: neither has a result file at the time of writing; both are in flight. The deck may only state their status on the day (ADR-002).

## Consequences

- The deck states the project's own weakest numbers (drift, the straight-line comparison, the ring radius, the residual step) in its own words, which costs a headline and buys credibility with the evaluators most likely to shortlist (ADR-003 governs how).
- "Novelty" as scored by a generalist screener may read lower than a competitor claiming a new network. Accepted: the PS owner is ISRO, and the audit's §11 comparison shows the field's strongest rivals are the ones with honest ablations (Agastya), not the ones with the biggest claims.
- Every sentence on the deck must trace to a file; the plan's §3 table and §6 metrics carry the mapping, and any claim without a file is removed rather than softened.
- The finale narrative is already set: the same measurement discipline applied to the phone's 401 Hz / 1 Hz data, with negatives published if that is what the data says (plan R8).

## Status

Accepted, 2026-09-10. Supersedes the "1.7×–43×" and "two-wheelers included" framing on the committed deck (`77f57e4`).

## Date

2026-09-10
