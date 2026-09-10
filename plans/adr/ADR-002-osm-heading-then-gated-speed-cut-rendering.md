# ADR-002: Build the heading-only OSM constraint first and the gated speed filter second as the two PS-coverage items; cut the 3D and rendering work

## Context

The PS names five components (audit §5, lines 100–104): Calibration Engine, AI Speed Filter running locally, Map-Matching Framework (offline OSM with kinematic constraints), GNSS+INS Fusion, Seamless Transition. Two are absent from the shipped path (audit §6 "critical unaddressed"): map-matching has no code in the deployed pipeline, and the AI speed filter is trained but opt-in, off by default and not on the device (`python/README.md` "So the speed net stays opt-in"; `android/README.md` "Not yet done"). With 5 days to the idea deadline and roughly 13 weeks to the finale, the project cannot build everything; a third of the app's Kotlin serves a Filament 3D orb, GPU benchmark and render tiers the PS never asks for (audit §7 "complexity without value"; `plans/shadownav-3d-mvp-web-deck.md` steps 1–4), and the app bundles Monaco map tiles.

Measured facts that decide the order:

- The dominant error is along-track: cross-track 18.6/75.5/173.7/377.7/473.6 m of a total 194/378/658/1086/1480 m at 10–180 s (`eval/results/kinematic.json` `cte_median_m`, `crse_median_m`). But the filter's cross-track is *worse* than a straight line's (6.4/44.0/136.1/326.0/361.3 m, `baseline_cv.json`) and than raw gyro heading hold (`baseline_gyro.json`), so heading has a fixable defect and an external heading reference has something to correct.
- The heading-only map constraint is low-risk by construction: it is safe on parallel roads where a lateral constraint is dangerous, it self-disables on zero candidates within 200 m, and it has no learned component to fail under distribution shift (open-track Track C). It runs on IO-VNBD as-is, so it can be ablated on the test fold *before* the deadline. It is in flight today with real Overpass data for four routes already fetched (`data/osm/`, `python/shadownav/map/`, `python/scripts/run_map_ablation.py` → `eval/results/kinematic_maphead.json`, `kinematic_maphead_off.json`).
- The speed filter is higher-risk: ungated it helps 9–13 % at 30–120 s and hurts 19 % at 180 s on 8 sequences (`eval/results/kinematic_speednet.json`; `python/README.md` ablation table), the bias flips sign between val and test, and Agastya's published ablation shows ungated ML is worse than classical (dossier §10). The gate must be designed and validated without touching the test fold, and the device path (ONNX Runtime Mobile, INT8, XNNPACK) has no toolchain in the repo yet. Its real payoff needs 401 Hz features that do not exist until the drive is replayed.
- The rendering work has PS relevance 0 and demo value 2 in the audit's feature table (§7) and consumes finale weeks on a project whose target is a low-end phone.

## Decision

1. **Heading-only OSM constraint first** (Fouque, Bonnifait & Bétaille 2008 form): road bearing as a course observation with a χ² gate against the gyro-propagated heading, applied only when all surviving candidates agree in bearing within ~5° and no junction is within lookahead; hard-disable on zero candidates within 200 m or inside a car park; never constrain lateral position. Offline ablation on the test fold is the acceptance test (plan A15); on-device with an Indian-city extract is Track B6.
2. **Confidence-gated learned speed filter second** (plan A16 / B5): the existing CNN+GRU (128,083 parameters, `speednet_training.json`) behind a gate that admits the correction only when its predicted σ and the filter's speed uncertainty justify it; ablation must show no horizon worse than control by more than 5 %; ONNX export and ONNX Runtime Mobile for the device. The deck may call it "built" only when `kinematic_speednet_gated.json` exists.
3. **Cut the 3D and rendering work**: no further hours on the Filament orb, bloom, icosphere shards, GPU benchmark or render tiers; the Monaco tiles are replaced by an Indian extent only when the map work needs one, otherwise the map is hidden in the demo; the React/Three web MVP is frozen as a replay surface. The code is left in place; it is simply not worked on or mentioned.

The order is: map constraint → gated speed filter → (finale) 401 Hz ablations. If the map constraint's ablation is negative, it stays in the codebase as a measured negative and the deck says so; that outcome does not change the order.

## Alternatives considered

1. **Speed filter first**, because the error is mostly along-track. Rejected: the speed filter cannot be validated on the device before the drive data exists, its 10 Hz gain is marginal and sign-unstable, and shipping it ungated repeats a failure a competitor has already published. The map constraint is the only PS component that can go from "absent" to "built and ablated" before 15 Sep.
2. **Valhalla Meili HMM map matching (lateral position + heading)**. Rejected for now: Newson & Krumm's lattice breaks with no candidate within 200 m — exactly tunnels and canyons — and a wrong lateral match corrupts a tightly coupled filter (PLAN.md §6 item 3; open-track Track C). Heading-only is the principled subset; Valhalla tiles remain the deployment target for the *extract*, not the matcher, in Track B6.
3. **Both components in parallel before the deadline**. Attempted today; three of four briefs died on a rate limit. The deck must not depend on either landing, so the order exists to say which one gets the remaining hours.
4. **Keep the 3D work for demo polish**. Rejected: the audit rates it 0 on PS relevance, it complicates the low-end story, and every finale hour it takes comes out of B1–B7, which are the only items that can move the PS target.

## Consequences

- Slide 3 shows Map-Matching and AI Speed Filter as boxes with their true status on submission day (built + ablated / built, unmeasured / next), never as shipped features by implication.
- The finale critical path becomes: drive CSV replay (B1) → residual step fix (B2) → heading ablation (B3) → 401 Hz ablations (B4) → gated speed on device (B5) → map on device (B6) → scenario drives (B7).
- The multi-level car-park scenario is explicitly a map dead zone (OSM terminates service roads at the entrance); the constraint's self-disable is the demonstrable behaviour there, and the deck says so rather than implying map coverage.
- Rendering code stays in the repo untouched; anyone reviving it must reopen this ADR.
- If the OSM ablation is negative, that is reported as a result under ADR-001; the constraint still ships gated because its cost is zero when disabled.

## Status

Accepted, 2026-09-10. The map constraint is in flight under another agent; the gated speed filter relaunches today.

## Date

2026-09-10
