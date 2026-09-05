# GNSS-Denied Navigation Demo — `gnss-demo.html`

Live-presentation UI for SIH26168: a smartphone-IMU dead-reckoning system holding a vehicle's position through a GNSS blackout and blending back on reacquisition. **Simulated data, no backend, one file.**

## Run it

Double-click `gnss-demo.html`. Works from `file://` with the network off. No libraries, no build step, no vendored files — everything (WebGL renderer, Canvas2D fallback, simulation, audio synthesis) is inline. Present in a maximised Chrome/Edge window at 1920×1080.

- `?tier=high` or `?tier=low` on the URL pins the render tier and disables auto-degrade (use `?tier=high` on a 30 Hz projector output — see Known gaps).
- Audio is off by default; turn it on with the AUDIO button or `M` (WebAudio needs a user gesture).

## Controls (all keyboard-reachable, no hover required)

| Key | Action |
|---|---|
| `Space` / `Enter` / `PageDown` / `PageUp` | Primary action: LOCKED→DEGRADING, DEGRADING→LOCKED (abort), BLACKOUT→REACQUIRING, REACQUIRING→BLACKOUT (re-fracture from current positions). Presenter clickers send PageDown/PageUp. |
| `J` / INTERFERENCE button | Interference-type loss (from LOCKED only): C/N₀ collapses within 0.5 s and AGC drops 6.5 dB, so the attribution logic reads `INTERFERENCE · AGC ↓` instead of `BLOCKAGE`. Same state machine afterwards. Included to demonstrate the attribution path; India's documented GNSS interference is aviation, not roads (PLAN §3.3) — do not pitch it as a road scenario. |
| `A` | Auto-cycle. Location-triggered: DEGRADING starts 4 s of travel before the tunnel portal, BLACKOUT lasts the tunnel (275 m at 11 m/s = 25 s), REACQUIRING at the exit portal, ~60 s locked per lap. |
| `D` | Debug panel |
| `M` | Audio on/off |
| `R` | Full reset to t = 0, deterministically |

Every transition is interruptible; τ (the fracture clock) is scrubbed, never restarted, so restore mid-fracture reverses from the current shard positions and blackout mid-heal re-fractures from where the shards are.

## What is on screen

**Signal orb** — an icosphere (320 faces) grouped at load into 84 irregular panels (HIGH) / 80 faces → 36 panels (LOW) by seeded region growing, each with an outer skin, inner skin and side walls. One scalar τ drives everything: shard displacement is a closed-form impulse + viscous damping + fading gravity trajectory, so reverse playback is exact. LOCKED: whole, 0.15 rad/s, cyan internal glow pulsing at 0.4 Hz. DEGRADING: seams open continuously with confidence, amber light through the cracks, irregular wobble. BLACKOUT: shards separate, sag, hang and rotate; interior dark; magenta light on edges only. REACQUIRING: 1.8 s ease-out reassembly, magenta→amber→cyan.

**Mote trail** — 64 (HIGH) / 44 (LOW) motes on an analytic knot curve through and past the shard cloud. Its phase advances with vehicle speed (stops when the vehicle stops). It is the dead-reckoning estimate: perfectly smooth while everything else is broken.

**Route plane** — 40-waypoint closed loop (≈1017 m, one long straight = the tunnel, three tight corners, a chicane, two scheduled 2 s stops per lap). Cyan chevron = fused position. During an outage: hollow slate chevron = ground truth, filled magenta chevron = INS-only estimate, amber link = error vector, ring = the filter's 2σ (turns amber when the truth falls outside it), magenta ribbon = estimate breadcrumb, slate ribbon = truth breadcrumb. Depth is compressed 0.62× so the whole loop stays in view — stylised, not to scale.

**Readouts** — mode label, confidence gauge (critically-damped needle; wobble amplitude = the confidence noise band), drift `% of distance travelled` with the AVNet field reference beneath it.

**Debug panel** — filter mode (`GNSS-FUSED` / `INS-ONLY`), motion state (derived: `< 0.3 m/s` idle → `|yaw| > 12°/s` turning → `a < −1.2 m/s²` braking → cruising), raw confidence, time since fix, reported 1σ/2σ and whether the truth is contained, vehicle kinematics, GNSS observables (satellites tracked/used, NavIC visible/used, mean C/N₀, AGC, loss-cause attribution), render tier/budgets/frame time, and the 60 s estimate-vs-truth divergence chart with the 2σ band dashed.

## Simulation model (as implemented)

- Fixed 100 Hz step; every random draw comes from seeded `mulberry32` streams (seed 20260905, shown in the header). Same seed → same run at any frame rate. Only human button timing is non-deterministic.
- Confidence: locked 99.2 ± 0.6 jitter; degrading 98→62 linear over 4 s; dead reckoning `62·exp(−t/45)` floored at 12; jitter band `±(0.5 + (100−C)·0.04)`, resampled at 8 Hz and fed through the needle spring.
- Drift readout: `0.0025 · distance_since_loss · (1 + 0.15 · turns_since_loss)` — the brief's formula shape with the coefficient reconciled to the research. The brief's `0.0045 %/m` is ~4× the AVNet field rate (0.64 % over 578 m ≈ 0.0011 %/m) and put the 275 m tunnel at the very top of the 0.3–1.2 % band the brief asks for; `0.0025` lands the tunnel at 0.66 %, consistent with the reference readout beneath it and with the simulated est−truth divergence. One constant, `DRIFT_COEF`.
- Estimate error model in blackout: white velocity noise (√t growth), gyro-bias random walk (±0.05°/s initial), ±1 % speed scale, a heading kick + lateral step at every turn onset. Reported 1σ = `0.5 + 0.55·√t + 0.35·turns` m. Measured over the tunnel outage: 1–3 m error at the exit, 100 % of samples inside 2σ.
- Reacquisition: the error is its own state variable and follows a critically-damped spring (ω = 2.3) to zero while riding on the moving truth. Two wrong versions were caught by the harness — springing the position toward the moving truth (lags 2v/ω ≈ 10 m) and recomputing the error after the truth advanced each step (lags ~12 m, then snaps at lock). Residual at re-lock: 0.04–0.08 m, no snap.
- GNSS observables: two loss signatures. Blockage — C/N₀ declines across satellites over seconds while AGC holds. Interference — C/N₀ collapses within 0.5 s and AGC drops. The loss-cause line is computed from the observables (C/N₀ slope and AGC delta, after a 0.4 s evidence window), not from the button that was pressed.
- Event visuals are driven by sim-time stamps: a 0.9 s magenta ring on the floor at the instant of loss, a 1.1 s cyan ring at the vehicle when the fix re-anchors, and rest→current tethers on every shard while it reseats.

## Where the research shows up

| On screen | Source |
|---|---|
| `REF · AVNET FIELD RESULT 0.64% OVER 578 m / 55 s TUNNEL` | dossier §1.1 — the fair like-for-like comparison, phone IMU only |
| `ESTIMATOR InEKF 21-STATE · SE₂(3)` | dossier §1.1 / PLAN §2.2 #3 — the MVP filter core |
| `LOSS CAUSE · BLOCKAGE · C/N₀ ↓ AGC =` | PLAN §2.1 degradation handler, open-track findings (C/N₀ trend + AGC sign) |
| `NavIC (IRNSS) VIS / IN FIX 2 / 0` | dossier §12a — an L1 phone sees 1–3 NavIC satellites, none contribute to the fix; instrumentation, not accuracy |
| 2σ ring + `CONTAINED IN 2σ` | PLAN §3.5 — "empirically calibrated coverage", never "guaranteed" |
| Blend-back with no visible jump | PLAN §2.2 #5, the PS's literal grading criterion |
| 10 Hz breadcrumbs / 100 Hz step | PS 10 Hz update requirement |

## Performance and fallbacks

- Render: main scene at full resolution on the MSAA default framebuffer; bloom from a ¼-resolution emissive-only glow buffer (shards act as occluders) with two separable blur passes, composited additively. DPR capped at 1.5 (HIGH) / 1.0 (LOW).
- Measured on an AMD Radeon integrated GPU (D3D11 ANGLE, Chrome) at 1920×1080 HIGH: median 16.7 ms, p95 17.4 ms, 0 frames over 22 ms in LOCKED and BLACKOUT. Debug-panel open adds a one-off ~100 ms layout frame.
- Auto-degrade: > 22 ms for 60 consecutive frames → LOW (≤ 40 shards, 500 particles, DPR 1, coarser glow buffer) and stays there. The shard set swaps only when the orb is whole so the re-tiling is invisible.
- WebGL unavailable or context lost → Canvas2D fallback: same camera, same shard kinematics (painter-sorted), core glow, motes, route, markers, all readouts. ~4 ms/frame.
- `prefers-reduced-motion`: fracture physics replaced by a 0.6 s cross-fade between the whole orb and the settled cloud; colours and state changes preserved.

## Validation performed

- Node harness on the simulation (`scratchpad/sweep.js`): lap time, tunnel duration, turn/stop counts, drift and divergence at reacquisition, 2σ containment, residual at re-lock.
- Playwright over `file://` (headless Chromium): console/page errors, every state transition, a seven-press interrupt mash, reset, auto toggle, forced Canvas2D, reduced motion, pinned LOW tier. Zero errors in all scenarios.
- Headed Chrome on the real GPU for frame-time statistics (above).

## Known gaps

See the delivery notes for the full list. The three least certain on an unfamiliar machine: (1) a 30 Hz mirrored/projector output makes every rAF interval 33 ms and trips the auto-degrade rule within 2 s on a perfectly healthy GPU — pin `?tier=high`; (2) the WebGL1 path (older Intel drivers, some Safari) compiles the same GLSL ES 1.00 shaders but was only exercised under WebGL2; (3) audio levels were set numerically, not by ear — check on the venue speakers.
