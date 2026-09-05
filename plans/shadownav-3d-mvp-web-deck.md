# Blueprint: ShadowNav v1 — Full-3D Android MVP + Web MVP + SIH26168 Pitch Deck

Status: **REVISED after adversarial review (2026-09-05)** — v1 was reviewed by an Opus-tier architect agent and returned verdict **NEEDS FIXES FIRST**, with 4 CRITICAL and 18 MAJOR findings. This revision addresses all of them; changes are marked **[FIX-n]** referencing the finding number below each affected step. See "Review changelog" at the end for the full finding list and disposition.
Created: 2026-09-05. Revised: 2026-09-05.
Repo: C:\code\DEAD-RECKONING (github.com/muhammedsayeedurrahman/ShadowNav, private, default branch `master`)
Workflow mode: **branch + PR**, merge to `master` as each step's own verification passes (not one long-lived integration branch — see Execution note).

**Baseline measured this session (2026-09-05, JDK: Android Studio's bundled JBR 21, via `android/gradlew.bat`):**
```
:shadownav-core:test    PASS (parity suite green)
:app:assembleDebug      PASS — app-debug.apk   = 12,716,984 bytes (~12.1 MiB)
:app:assembleRelease    PASS — app-release.apk =  2,226,384 bytes (~2.12 MiB)
```
This confirms `PLAN.md`'s "2.2 MB release APK" and "12 MB debug APK" claims and establishes the exact before-numbers every later step's size deltas are measured against.

## Objective

Ship three deliverables against SIH26168 (ISRO — smartphone-IMU vehicle dead reckoning through GNSS blackouts):

1. A production-grade Android app with full 3D rendering — a Filament-rendered status orb, and a real-world map route scene — wired to the real estimator and real sensor/GNSS data, still usable on the project's documented low-end-hardware floor (API 29) via a capability-gated fallback.
2. A deployable web MVP that reuses `demo/gnss-demo.html`'s proven rendering techniques but runs on real data and a real map, instead of a seeded simulation over an arbitrary plane.
3. A SIH26168 pitch deck whose every technical claim traces to already-committed, already-verified sources.

## Mandatory pre-reads (do not re-derive; cite instead)

- `CLAUDE.md`, `PLAN.md`, `research/SIH26168-dead-reckoning-research.md`, `research/SIH26168-open-track-findings.md`, `research/SIH26168-external-review-response.md`, `python/README.md`, `shared/README.md`, `eval/results/*.json`, `demo/README.md` + `demo/gnss-demo.html`.
- **[FIX-1]** `PLAN.md` §Phase 1 results table (lines ~169-175) is **stale** — it reads 189/372/658/1056/1463 m, 1.6x-43.4x. The actual committed `eval/results/kinematic.json` vs `eval/results/baseline_naive.json` gives **180/368/640/1071/1474 m, gain 1.7x-43.0x at the 10s/30s/60s/120s/180s horizons** — this matches `README.md`'s status table exactly. **Use `README.md`'s numbers and `eval/results/*.json` directly everywhere in this plan and in the pitch deck. Never quote `PLAN.md`'s Phase 1 table until Step 13 corrects it.** The correct composite figure is **1.7x-43.0x**, not "1.7x-43.4x" (a mixed figure that appears in neither table and must not be used).

## Non-negotiable constraints (apply to every step)

1. **The low-end-device story must not regress.** Measured gain: 43.0x drift-improvement over naive strapdown at 180s (see FIX-1 numbers above), on a 2.2 MB APK, minSdk 29. Every new rendering path is capability-gated: `FULL_3D` / `REDUCED_3D` / `CANVAS_2D`, with `CANVAS_2D` being today's exact, unmodified `TrackView.kt` — never deleted, always the floor.
2. **Never invent a technical claim.** Every number in the app UI or the pitch deck must exist in `eval/results/`, `PLAN.md` (once corrected per FIX-1), or the research docs.
3. **Preserve existing accessibility work** (`Ui.kt`, `MainActivity.kt`, commit `a5ac728`): WCAG AA contrast, 60dp driving touch targets, focus rings, `contentDescription`s. New 3D/map UI must meet or exceed these.
4. **Don't silently change the estimator, and know exactly where its boundary is.** **[FIX-5]** The parity-proven boundary is `android/shadownav-core` (pure Kotlin/JVM, covered by `ParityTest.kt`, verified against Python golden vectors) — this module is never touched by this plan. `NavigationEngine.kt` (package `com.shadownav.app`, in the `app` module) is **plumbing that reads `shadownav-core`, not part of the parity-covered boundary** — it can be touched, but `:shadownav-core:test` passing proves nothing about a change made there. Any change to `NavigationEngine.kt` needs its own justification and, where practical, its own app-module test — and per FIX-5's resolution below, this plan avoids touching it at all by keeping new UI state (like "time since this mode started") computed in the UI layer from the existing 10Hz `Snapshot` stream, not added to `NavigationEngine` itself.
5. **A map basemap is a rendering concern, not a filter concern.** `PLAN.md` §2.2 item #12 (Valhalla Meili map-matching, Phase 2, not started) corrects the position *estimate*. This plan's map work (Step 3, Step 8) is visual only, built from the *unmodified* filter output. Never wire map/tile data into `NavigationEngine` or any filter code.
6. **Map tiles are bundled, not fetched — by design, not just for the tunnel.** **[FIX-13, FIX-14]** Free hosted tile providers (MapTiler, Stadia, plain OSM raster) either require an API key or prohibit bulk/offline downloading under their ToS — and the app's own `AndroidManifest.xml` currently has **no `INTERNET` permission at all**, which is itself part of the project's sovereignty pitch (`PLAN.md` §3.8, "on-device, no cloud"). Resolve this the strongest way rather than the weakest: **the Android app bundles a pre-built offline vector-tile extract (PMTiles or MBTiles, built once from OSM data with a tool such as Planetiler/Protomaps, ODbL-licensed with attribution) covering only the specific demo route as an asset.** This needs **no `INTERNET` permission, no API key, no per-request billing, and no ToS violation** — it strengthens the no-cloud pitch instead of contradicting it. The trade-off (only the pre-selected demo route has a map, not arbitrary locations) is the right one for this project's actual scope and must be stated as a known limitation, not hidden.
7. **A real map makes the project's own honestly-reported numbers look different, and that's fine as long as it's planned for, not discovered live.** **[FIX-15]** Two real effects a real basemap introduces: (a) 77-108% drift (`PLAN.md`, `README.md`) reads as "an estimate" on an abstract grid but as "driving through buildings" on a real map; (b) the PS's own multi-storey-car-park scenario has no OSM road network at all (`PLAN.md` risk #3) and will render as blank ground. Both are accepted trade-offs of adding a real map — Step 3 must document them explicitly, and Step 11 (deck) must be briefed to answer "why is the vehicle off the road" if asked.

## Dependency graph

```
Step 0 (Ground truth, corrections, cross-cutting decisions)
        │
        ├──────────────┬──────────────────┐
        ▼              ▼                  ▼
Step 1 (Android:   Step 6 (Web: MVP   Step 10 (Pitch:
capability probe   scaffold, 6a+6b)   competition research)
+ orb engine wiring)   │                  │
        │              ▼                  ▼
        ▼          Step 7 (Web:       Step 11 (Pitch:
Step 2 (Android:   real data wiring)  build the deck)
Filament orb)          │
        │              ▼
        ▼          Step 8 (Web: real
Step 3 (Android:   map basemap)
map route scene)       │
        │              ▼
        ▼          Step 9 (Web: UX
Step 4 (Android:   polish + deploy)
UX polish)             │
        │              │
        ▼              │
Step 5 (Android:       │
on-device validation)  │
        └───────┬──────┘
                ▼
    Step 12 (Security review + release
             signing + on-device release validation)
                │
                ▼
    Step 13 (Final cross-surface verify,
             PLAN.md/README.md corrections)
```

Parallel groups: `{1, 6, 10}` (after 0) → `{2, 7}` → `{3 (Android only), 8 (needs 7)}` — **3 and 8 do not depend on each other**, and 11 (needs 10) can run alongside either → `{4 (needs 3), 9 (needs 8)}` → `5 (needs 4)` → `12 (needs 5 and 9)` → `13 (needs 11 and 12)`.

## Anti-patterns already ruled out

- Re-running research already answered in the research docs.
- Touching `python/shadownav/filter/*` or `android/shadownav-core`.
- Replacing `demo/gnss-demo.html` in place.
- **[FIX-25]** Assuming Compose is needed: it is not. This plan uses **raw `com.google.android.filament:filament-android`** (a plain `SurfaceView`/`TextureView` API, no Compose dependency), confirmed via live lookup this session (Maven Central `filament-android` 1.75.1, released ~11 days ago) — not SceneView, whose current 4.x line is Compose-native and (per its own marketing copy, "~5MB footprint") would roughly double the entire app's current size just for the Compose + SceneView layer. This is now an explicit, recorded decision (Step 1), not an incidental one.
- Shipping a release build signed with the debug keystore (current: `android/app/build.gradle.kts:33`) and calling it shippable — Step 12 fixes this, **and now also actually installs and exercises that signed release build on the connected device (FIX-11)**, not just signs and verifies it.
- Confusing the basemap-rendering steps with `PLAN.md` #12's map-matching filter feature.
- **[FIX-2]** Picking a map SDK, then separately picking a 3D engine, then assuming they visually composite. They don't, cheaply: Filament and MapLibre Native each own an independent GL context/surface, and there is no simple "layer one on top of the other" API on Android. **Resolution: Filament is used only for the self-contained status orb (Step 2), which never needs to sit over a map. The route scene (Step 3) is built natively as MapLibre style layers (line/circle/symbol for trails, chevron, and the confidence ring) — MapLibre's own camera pitch/bearing gives a 3D-perspective look without a second GL engine.** This is decided once, in Step 0/1, not discovered mid-implementation.

---

## Step 0 — Ground truth, corrections & cross-cutting decisions

**Model tier:** default (Sonnet). No rendering code in this step — it is documentation + a handful of small, low-risk decisions everything else depends on.
**Depends on:** none. **Parallel with:** nothing (everything else depends on this).
**Branch:** `chore/plan-ground-truth` (small PR, docs + `AndroidManifest.xml`/`PLAN.md` edits only)

### Why this step exists

The original v1 plan discovered several of these facts mid-step, which is exactly the kind of thing the review flagged as unexecutable-by-a-cold-agent. Settling them once, up front, means Steps 1-3 don't have to make architectural guesses.

### Task

1. **[FIX-1]** Correct `PLAN.md`'s Phase 1 results table to match `eval/results/kinematic.json` / `baseline_naive.json` exactly (180/368/640/1071/1474 m, 1.7x-43.0x) — it currently reads stale numbers from before the last regeneration.
2. **[FIX-20]** Reconcile `README.md`'s self-contradiction on the learned speed front end: line ~30/54 says "trained, opt-in," line ~65 says "specified and wired but untrained," and `PLAN.md` also says "not yet trained." Check `eval/results/speednet_training.json` and `eval/results/kinematic_speednet.json` (both exist) and `shared/README.md`'s documented `sigma_scale` of 3.27x (a *fitted* value) — these indicate it **is** trained. Fix whichever doc-line is wrong so `README.md` and `PLAN.md` agree before either is quoted in the pitch deck.
3. **[FIX-4]** Name the specific demo route: pick (or confirm with the user) an actual GNSS-blackout location — ideally a real tunnel — reachable with the connected physical device, with known bounding-box coordinates. Record it (name, lat/lon bounding box, approximate length, the phone model being used) in a new `PLAN.md` §7 open-question resolution or a new `demo/DEMO_ROUTE.md`. Steps 3 and 5 depend on this existing.
4. **[FIX-26]** Surface the Play Store question now, not at Step 12: ask the user whether Play Store submission is actually in scope for this timeline. Record the answer in `PLAN.md`. This affects Step 1's size/ABI budget (a Play Store app bundle handles per-device ABI splitting for you; a sideloaded APK does not) and Step 3's tile-licensing posture.
5. **[FIX-6]** Record the bundled-offline-tiles decision (constraint 6 above) in `PLAN.md` §2.4 (Tech stack): no map API key, no `INTERNET` permission added, PMTiles/MBTiles extract of the demo route only, built via Planetiler/Protomaps from OSM (ODbL, attribution required).
6. Confirm `android/gradlew.bat` builds successfully in the actual dev environment being used for this work — **already done this session**: baseline `:shadownav-core:test`, `:app:assembleDebug`, `:app:assembleRelease` all pass, using Android Studio's bundled JBR (`C:\Program Files\Android\Android Studio\jbr`) as `JAVA_HOME` (the previously-configured `JAVA_HOME` pointed at a non-existent path). Record this JDK path in `android/README.md` or a `CONTRIBUTING.md` note so the next session doesn't have to rediscover it.

### Verification

Manual: all facts above are recorded in the repo (not just in this plan), and `./gradlew :shadownav-core:test :app:assembleDebug :app:assembleRelease` still passes after any doc-only edits (it should — nothing here touches source).

### Exit criteria

- `PLAN.md` and `README.md` agree with `eval/results/*.json` and with each other on every number this plan will later quote.
- A specific demo route with real coordinates exists in the repo.
- Play Store scope decision recorded.
- Bundled-tiles decision recorded.

### Rollback

Revert commit — docs only, nothing downstream has built on wrong facts yet.

---

## Step 1 — Android: capability probe + Filament orb-engine wiring + size/ABI budget

**Model tier:** strongest (Opus) — the architectural decisions here (engine choice, ABI/size policy, view-hosting model) gate everything downstream.
**Depends on:** Step 0. **Parallel with:** Step 6, Step 10.
**Branch:** `feat/android-3d-capability-gate`

### Context brief

`android/app/build.gradle.kts` has zero rendering dependencies beyond `androidx.appcompat`/`material` (AGP 8.7.3, Kotlin 2.0.21, compileSdk 35, minSdk 29 — confirmed via `libs.versions.toml` and a live baseline build this session). No Compose, no OpenGL/3D dependency exists today. Per the anti-patterns section, this plan uses **raw Filament (`com.google.android.filament:filament-android`, currently 1.75.1 on Maven Central)** for the status orb only — not SceneView, which is Compose-native. Confirm the exact pinned version via `search-first` at execution time (versions move); do not hardcode 1.75.1 without re-checking.

`demo/gnss-demo.html` already solved "full 3D on weak hardware": HIGH tier auto-degrades to LOW after 60 consecutive frames over 22ms, falls back to Canvas2D (~4ms/frame) if WebGL is unavailable. Reproduce the same three-tier shape: `FULL_3D` / `REDUCED_3D` / `CANVAS_2D` (`TrackView.kt`, unmodified, the permanent floor).

### Task

1. Confirm current Filament Maven coordinates/version via `search-first` (done once this session: 1.75.1, ~11 days old at time of writing — re-verify at execution time since this moves fast). Add to `libs.versions.toml` + `android/app/build.gradle.kts`.
2. **[FIX-12]** Set an explicit **APK size ceiling** before adding anything: given the baseline release APK is 2,226,384 bytes and the project's own hardware decision targets "low-end, limited storage," propose a ceiling (e.g., 8-10 MB release, informed by Step 0's Play Store-scope answer — an App Bundle's per-device delivery changes this budget materially vs. a universal sideloaded APK) and get it confirmed rather than assumed. **Do not repeat the ungrounded "Filament ships a small runtime" claim from v1** — measure it. Filament and (Step 3's) MapLibre Native both ship per-ABI native `.so` files that R8/resource-shrink cannot touch; decide now whether to ship `armeabi-v7a` + `arm64-v8a` only (covers the vast majority of real Android hardware, roughly halves the native-lib payload vs. all four ABIs) via `ndk { abiFilters += listOf(...) }` or ABI splits, and record the decision with its rationale.
3. Add the Filament dependency, then run `./gradlew :app:assembleRelease` and diff `app-release.apk` size against this session's baseline (2,226,384 bytes) via `unzip -l` or APK Analyzer. If the delta blows the ceiling from task 2, this is a **blocking finding** — stop and revisit the ceiling or the engine choice before proceeding, per the plan mutation protocol's abandon clause.
4. **[FIX-21]** Decide, and document, three integration-model questions before writing the orb view:
   - `SurfaceView` vs `TextureView` for the Filament surface (SurfaceView is lower-overhead but composes awkwardly inside a `ScrollView`/rounded-corner `card()`; TextureView composites like a normal View at some performance cost — given the orb sits in `MainActivity`'s header, outside the `ScrollView` entirely, `SurfaceView` is the likely right call, but confirm against the actual layout).
   - Who owns the single Filament `Engine` instance and its teardown. Filament strongly prefers one shared `Engine` for the process; both Step 2 (orb) and Step 3 (route scene, if it ends up using Filament rather than pure-MapLibre — it shouldn't, per the anti-pattern fix, but confirm no other consumer appears) must not each create their own. Recommend a small `FilamentHost` singleton or an `Application`-scoped holder, created lazily and destroyed in a lifecycle-aware way (there is no existing `onDestroy` teardown path for this today — `MainActivity.onDestroy` only unbinds the service).
   - Where the orb lives in the existing `ScrollView`-based layout (`MainActivity.buildUi()`) — recommend the header (outside the scrolling column), consistent with Step 2's plan.
5. **[FIX-9]** Design `DeviceCapabilityProbe` so its **tier-decision logic is a plain, dependency-free Kotlin function** (`fun decideTier(measurements: CapabilityMeasurements): RenderTier`) that takes already-measured inputs and is unit-testable with plain JUnit — **no Robolectric, no androidx.test dependency needed**, matching the project's existing pattern of keeping logic testable without the Android framework wherever possible (`shadownav-core` is pure-JVM for exactly this reason). Only the *measurement* code (reading `ActivityManager.MemoryInfo`, running the actual GPU probe) needs to touch Android APIs, and that part is not unit-tested here — it's exercised for real in Step 5's on-device validation.
6. **[FIX-8]** Fix the capability-probe methodology itself: a naive "render N frames, measure wall-clock ms/frame" is **vsync-limited on a 60Hz display** — a flagship and a low-end device both measure ~16.7ms per presented frame regardless of actual GPU headroom, which defeats the entire point of the probe. Instead, measure **GPU work per frame**, not frame interval: either render to an off-screen target in a tight, unthrottled loop (no `Choreographer`/vsync gating) and measure wall-clock time for a fixed amount of GPU work, or use `Window.OnFrameMetricsAvailableListener`'s reported GPU duration once a real frame is on screen. (Also: `demo/README.md`'s auto-degrade rule is a *frame-time* heuristic, not a "GPU-tier heuristic" as v1 of this plan mis-cited it — cite it correctly as evidence that frame-time-based heuristics need care, e.g. its own noted failure mode of a 30Hz mirrored output tripping auto-degrade on healthy hardware.)
7. Wire the `RenderTier` sealed interface (`FULL_3D`, `REDUCED_3D`, `CANVAS_2D`), persisted via `SharedPreferences`, with a manual override for Step 5's on-device testing.
8. **[FIX-10]** Add a mandatory **on-device smoke benchmark** to this step's exit criteria — the connected physical device is already available; don't wait until Step 5 to get the first real signal on whether the chosen engine even runs acceptably. This is a smoke test (does it render, roughly how fast), not the full battery/thermal/frame-time study that stays in Step 5.
9. Run `./gradlew :shadownav-core:test` to confirm the estimator boundary held (it should — separate Gradle module, untouched).

### Verification

```
./gradlew :app:assembleDebug
./gradlew :app:assembleRelease   # compare size against 2,226,384 bytes baseline
./gradlew :shadownav-core:test
./gradlew :app:testDebugUnitTest    # DeviceCapabilityProbe.decideTier() unit tests, plain JUnit
# On-device: install debug build, run the Filament smoke benchmark, confirm it renders
# and report the measured tier.
```

### Exit criteria

- Filament dependency compiles; release APK size delta recorded against the 2,226,384-byte baseline and checked against the ceiling from task 2.
- ABI policy decided and applied.
- `decideTier()` has plain-JUnit unit tests (no Android framework dependency) covering the tier boundaries.
- SurfaceView/TextureView, Engine-ownership, and ScrollView-placement decisions recorded.
- On-device smoke benchmark run and its result recorded — if the engine cannot render acceptably even in a reduced form on the connected device, invoke the plan mutation protocol's abandon clause **now**, not after Steps 2-5 are built and merged.
- `PLAN.md` §2.4 updated with the engine choice, version, and measured size delta.
- `shadownav-core` test suite passes unmodified.

### Rollback

This step is expected to merge to `master` once green (per the Execution note — no long-lived branch). If the on-device smoke benchmark fails the abandon threshold, do not merge; instead land only the `RenderTier`/`CANVAS_2D`-only state (a no-op for now) and record the abandonment decision in `PLAN.md`'s risk register.

---

## Step 2 — Android: Filament status orb

**Model tier:** default (Sonnet).
**Depends on:** Step 1. **Parallel with:** Step 7.
**Branch:** `feat/android-3d-status-orb`

### Context brief

Port `demo/gnss-demo.html`'s signal orb (whole+glowing `LOCKED`, seams+amber `DEGRADING`, shards+dark+magenta `BLACKOUT`, 1.8s ease-out reassembly `REACQUIRING`) as a Filament scene. The orb is a self-contained header widget — it does **not** sit over the map (that's Step 3's separate, MapLibre-only concern, per the FIX-2 architecture split) — so it has no GL-compositing problem to solve.

**[FIX-6 — state mapping]** `NavigationEngine.Snapshot.mode` only carries `AIDED`/`DEGRADED`/`DEAD_RECKONING`/`REACQUIRING`, but `MainActivity.render()` actually distinguishes **six** UI states: `!hasFix → "ACQUIRING"`, `simulatedBlackout → "SIMULATED BLACKOUT"`, then the four mode values — and that extra handling exists specifically because `mode` reads `AIDED` before the first fix ever lands, and showing a whole/glowing/cyan orb there would visually assert a GNSS lock with zero satellites, which `MainActivity.kt`'s own comment explicitly calls out as wrong. **The orb must consume the same six-way state, not `mode` alone.**

**[FIX-5 — no engine edit]** Do not add a "time since this mode started" field to `NavigationEngine`/`Snapshot` — that module is plumbing outside the parity-covered boundary but changing it still needs its own justification this plan doesn't want to spend. Instead, **derive the time-in-mode clock in the UI layer**: `MainActivity`'s existing 10Hz `render()` loop already observes `s.mode` (and the five other states) on every tick; track "ticks since the observed state last changed" there and hand that derived duration to the orb view alongside the state itself.

### Task

1. Extract `MainActivity.render()`'s existing six-way `when` block (lines ~248-255, the one that currently produces `chipText`/`chipColour`) into a shared `fun uiState(s: NavigationEngine.Snapshot): OrbState` (or similar), consumed by **both** `StatusChip` and the new orb view, so the two can never diverge in what they announce.
2. Add a `FilamentOrbView` custom View, gated by `RenderTier` (per Step 1): `FULL_3D` full orb, `REDUCED_3D` simplified (fewer panels, no bloom-equivalent), `CANVAS_2D` nothing new — `StatusChip` alone, unchanged.
3. **[FIX-22 — no per-frame engine calls]** The orb's render loop must **never call `service.engine.snapshot()` from a frame callback.** `snapshot()` runs under the same lock the IMU callback holds at ~401 Hz measured, and formats a debug string on every call — driving it from a 60Hz Filament/Choreographer loop would be a 6x increase in lock contention on the sensor-critical path. Instead, the orb consumes the same 10Hz `push`-style update `MainActivity.render()` already produces (extend that call site to also push to the orb) and **interpolates visually between samples** for smooth 60fps animation without re-touching the engine more often than today.
4. Implement the five-plus-blackout-state visual treatment (add an explicit "acquiring" treatment — e.g. a dim, static, unlit orb — distinct from the four `GnssMode` states) using `Ui.kt`'s existing `Palette` constants.
5. `contentDescription` on the orb must restate exactly what `StatusChip` announces (via the shared `uiState()` function from task 1) — never a second, divergent announcement.
6. **[FIX-7 — testable exit criterion]** Do not test state transitions by "forcing state in `NavigationEngine`" — that's both an engine edit (banned) and, for `DEGRADED` specifically, not actually reachable that way (`GnssFsm`'s `DEGRADED` condition depends on live satellite/C-N0/accuracy values `NavigationEngine` computes from real GNSS input; the existing SIMULATE TUNNEL button only reaches `DEAD_RECKONING`). Instead, build a small **UI-layer debug harness** — a test-only code path that feeds synthetic `OrbState` values (from task 1's shared type) directly into the orb and chip views, bypassing the engine entirely. This is a legitimate, engine-untouched way to exercise all six states.

### Verification

```
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
# Manual: use the Step 2.6 debug harness to drive the orb through all six states,
# in all three RenderTier paths (forced via Step 1's manual override).
```

### Exit criteria

- Orb correctly renders all six UI states (five `GnssMode`-driven plus the pre-fix "acquiring" state) via the debug harness, without any engine modification.
- `CANVAS_2D` tier shows no orb, zero regression to the existing header.
- Orb's `contentDescription` is provably identical to `StatusChip`'s (same shared function).
- No frame callback anywhere calls `snapshot()` — verified by code review, not just testing.

### Rollback

Revert branch (or, once merged per the Execution note, revert the merge commit). `StatusChip`-only behavior is preserved.

---

## Step 3 — Android: real-world map route scene

**Model tier:** default (Sonnet), tile-build tooling confirmed via `search-first`.
**Depends on:** Step 2 (for the shared `uiState`/state-plumbing pattern; the map itself doesn't depend on the orb). **Parallel with:** Step 8, Step 11.
**Branch:** `feat/android-map-route-scene`

### Context brief

**This step merges what were two separate steps in v1 of this plan** (a Filament 3D route scene, then a map basemap layered under it) **because that split assumed Filament and a map SDK can be visually composited on Android, which they cannot without a nontrivial custom-layer host.** Per constraint 6 and the anti-patterns section: this step builds the route scene entirely as **MapLibre Native** style layers — no second GL engine, no compositing problem. MapLibre's own camera pitch/bearing gives a legitimate 3D-perspective look; if the chosen map style has building-height data, extrusion adds real 3D geometry too, at no extra engine cost.

`TrackView.kt` today draws: two polylines (aided vs dead-reckoned), a calibrated confidence ring (`sigmaM * conformalLambda * 2.146` — **load-bearing, never approximate**, `TrackView.kt` lines ~22-25/147-151), a heading chevron. Port these as MapLibre layers: a `line` layer per trail, a `circle`/custom layer for the ring, a `symbol` layer for the chevron. **[FIX-24]** `MainActivity.kt` reads `track.conformalLambda` as a public property (set once at `onCreate`, read every render tick to compute the headline "90% RADIUS" metric) — preserve this exact coupling if `TrackView` becomes a wrapper delegating to a MapLibre-backed implementation; don't let a refactor silently break it.

Do not fabricate ground truth or an "error vector" (the demo's out-of-2σ indicator only exists because it has simulated ground truth; the real app has none).

**[FIX-6 tiles]** Per the non-negotiable constraints, tiles are a **bundled offline PMTiles/MBTiles extract of the Step 0-named demo route only** — no `INTERNET` permission added, no API key, no ToS exposure. **[FIX-14]** This is a deliberate, documented trade-off: the map only covers the pre-selected demo route, not arbitrary locations — correct for this project's actual scope, and it strengthens rather than weakens the "on-device, no cloud" pitch (`PLAN.md` §3.8) since it needs literally zero network access, ever.

**[FIX-15 — new risks to document, not hide]** Adding a real map introduces two effects worth calling out explicitly in this step's own notes (and later briefed to Step 11's deck): (a) the project's honestly-reported 77-108% drift will visually read as "driving through buildings/off the road" rather than "an abstract estimate with error bars" — this is a real, currently-true number and the map doesn't change it, only its visual legibility; (b) if the demo route's outage happens to include something like a multi-storey car park, `PLAN.md` risk #3 already notes OSM has no road network there, so that stretch of the bundled map will show as blank ground with no route line to match against — expected, not a bug.

### Task

1. Use `search-first` to confirm current MapLibre Native Android integration (Maven coordinates, current version, and confirm it remains View-based/non-Compose) and current tooling for building a PMTiles/MBTiles extract from OSM data for a small bounding box (Planetiler or Protomaps' `tilezen`/similar, whichever is current and simplest for a single small region).
2. Build the offline tile extract for the Step 0-named demo route's bounding box; bundle it as an app asset (record its size — it counts against Step 1's APK ceiling).
3. Add MapLibre Native as a dependency (separate `RenderTier`-gated integration point from Filament — `FULL_3D`/`REDUCED_3D` get the map+route layers, `CANVAS_2D` keeps `TrackView.kt`'s exact current grid, unmodified).
4. Implement the trail/chevron/ring as MapLibre style layers, fed from the same `TrackView.push(snapshot)` data path (no second data path) — reproduce the `sigmaM * conformalLambda * 2.146` ring math exactly.
5. Confirm the Step 0-named route's bundled tiles actually render (this is a local-asset load, so "confirm with network off" is nearly automatic here — but verify it explicitly, since a code path that silently falls back to a network fetch would defeat the whole point).
6. Preserve `TrackView.push()`'s existing `contentDescription` announcement pattern regardless of which renderer backend is active.
7. Display the OSM/PMTiles attribution required by ODbL, visibly and accessibly.
8. Document the two new risks (drift-looks-worse-on-a-real-map, no-road-in-car-parks) in this step's PR description and in a short `PLAN.md` note — this is the artifact Step 11 will read before writing the deck's "why is it off the road" answer.

### Verification

```
./gradlew :app:assembleDebug
# Manual: drive a simulated blackout (SIMULATE TUNNEL) with airplane mode ON throughout,
# confirm the bundled route map + trails + ring render with zero network access at any point.
```

### Exit criteria

- Real bundled map renders under the route scene in `FULL_3D`/`REDUCED_3D`, with zero network dependency, verified with airplane mode on.
- `CANVAS_2D` tier is behaviourally identical to today's `TrackView.kt` (verified by a behaviour/screenshot diff, since the underlying class may now be a delegating wrapper — see FIX-23).
- `track.conformalLambda`'s public-property coupling to `MainActivity`'s "90% RADIUS" metric still works.
- No filter/estimator code touched; a short note distinguishes this from `PLAN.md` #12.
- Attribution displayed.
- New-risks note written for Step 11.

### Rollback

Revert branch/merge commit. `TrackView.kt`'s `CANVAS_2D` path is untouched throughout and remains available as the sole renderer if this step is reverted.

---

## Step 4 — Android: advanced UI/UX pass (motion, transitions, polish)

**Model tier:** default (Sonnet).
**Depends on:** Step 3. **Parallel with:** Step 9.
**Branch:** `feat/android-ux-polish`

### Context brief

Motion/transition polish across the orb (Step 2) and map route scene (Step 3) — not new features. Read every comment in `Ui.kt` before touching anything; several constraints there (e.g. `SLATE`'s exact colour value) exist because of a specific documented past failure (a contrast measurement that failed AA).

### Task

1. Transition animations between the six UI states (reassembly easing on the orb, a corresponding subtle transition on the map layers, camera easing) respecting Android's "Remove animations" accessibility setting / `ValueAnimator.areAnimatorsEnabled()`, mirroring the demo's `prefers-reduced-motion` handling (cross-fade instead of physics).
2. Extend (don't fork) `Ui.kt`'s existing `card()`/`label()`/`value()`/`mono()` vocabulary for any new UI chrome.
3. Contrast-audit every new colour combination, including text/controls drawn over real map imagery (map tiles introduce new, non-uniform backgrounds — check contrast against the map's actual rendered colours, not just a flat assumed background), documenting ratios as the existing code does.
4. `contentDescription` on every new stateful element, following the existing pattern.

### Verification

```
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
# Manual accessibility pass: TalkBack, keyboard/switch navigation, "Remove animations" on.
```

### Exit criteria

- Every new UI element has a documented ≥4.5:1 (or ≥3:1 large-text) contrast ratio and a `contentDescription`.
- Reduced-motion path verified.
- No regression to existing `Ui.kt` component behavior.

### Rollback

Revert branch/merge commit.

---

## Step 5 — Android: on-device validation (debug build)

**Model tier:** default (Sonnet).
**Depends on:** Step 4. **Parallel with:** none.
**Branch:** `feat/android-on-device-validation`

### Context brief

`PLAN.md` Phase E: "no on-device latency, battery or thermal measurement" — close that gap for the debug build here; the **release** build's on-device validation is Step 12's job (per FIX-11 below), since a real signed release APK doesn't exist until then.

### Task

1. Install the debug build on the connected device.
2. Measure frame time per `RenderTier` for orb + map scene across all six UI states (via Step 2's debug harness plus the SIMULATE TUNNEL button); battery drain (`dumpsys batterystats` before/after, or Energy Profiler); thermal signs over a 10+ minute run; **measured IMU rate** (already surfaced in diagnostics — "IMU %.0f Hz measured" — confirm rendering load doesn't degrade it, since that would silently corrupt the estimator's input).
3. Confirm the Step 3 bundled tiles render correctly on-device with airplane mode on for the real duration of a simulated outage.
4. Tune Step 1's capability-probe threshold against these real measurements if needed.
5. Record results in `android/ON_DEVICE_VALIDATION.md` or a `PLAN.md` Phase E addendum.

### Verification

Manual, on-device — no automated substitute.

### Exit criteria

- Written record of frame time, battery, thermal, offline-tile behaviour, and confirmed-unaffected IMU rate.
- Capability-probe tier confirmed/tuned for this device.
- Any finding that rendering degrades IMU sampling is a **blocking finding** carried into Step 12 — do not ship a build where rendering starves the sensor pipeline.

### Rollback

Documentation only; tune the Step 1 threshold via a small follow-up commit if needed.

---

## Step 6 — Web: MVP scaffold (6a: decision + scaffold, 6b: renderer port)

**[FIX-19]** Split into two PRs — the original single step bundled a framework decision, a full scaffold, *and* porting the demo's entire renderer (84-panel seeded-region-growing icosphere, closed-form shard physics, ¼-res emissive bloom with two separable blur passes, MSAA, HIGH/LOW tiering, Canvas2D fallback), which is too much for one PR.

**Model tier:** strongest (Opus) for 6a's framework decision; default (Sonnet) for 6b.
**Depends on:** Step 0. **Parallel with:** Step 1, Step 10.
**Branches:** `feat/web-mvp-scaffold` (6a), `feat/web-renderer-port` (6b, depends on 6a)

### Context brief

No web app exists — only `demo/gnss-demo.html`, explicitly single-file, `file://`, **no backend, no build step** (`demo/README.md`). It is the design/rendering reference, not a file to keep extending.

**[FIX-18]** Do **not** design a backend API layer. The actual data need (per Step 7) is a static, build-time JSON export of one representative session — no server, no runtime API, no input-validation/rate-limiting surface to secure later. This removes an entire unnecessary deploy target and a chunk of Step 12's review scope.

### Task (6a)

1. `search-first` to confirm current best practice: Vite + React + TypeScript + Three.js is the working default (the demo's WebGL concepts — icosphere, bloom-via-separable-blur, MSAA — map onto Three.js primitives) — confirm current versions, and whether a lighter vanilla+Vite path suits a closer port of the demo's inline code better. Record the decision in `frontend/README.md`.
2. Scaffold `frontend/` (sibling to `android/`, `python/`) with the chosen stack and **a static-data-file contract**, not an API contract: document in `frontend/README.md` that the app loads a bundled/fetched static JSON file produced by Step 7's Python export, nothing else.
3. Land one placeholder scene (not the full renderer) to prove the build pipeline works end-to-end.

### Task (6b)

1. Port the demo's rendering techniques into componentized, reviewable modules: the orb/shard system, bloom pass, tier system, Canvas2D fallback.
2. Do not modify `demo/gnss-demo.html`.

### Verification

```
cd frontend && npm install && npm run build
npm run dev
```

### Exit criteria

- `frontend/` builds and serves a page; 6a proves the pipeline with a placeholder, 6b reproduces the demo's core visuals componentized.
- `frontend/README.md` states the static-data-file contract explicitly (no API layer).

### Rollback

Revert branch(es) / delete `frontend/` — nothing else depends on it yet.

---

## Step 7 — Web: real data wiring

**Model tier:** default (Sonnet).
**Depends on:** Step 6b. **Parallel with:** Step 2.
**Branch:** `feat/web-real-data`

### Context brief

Connect the Step 6 scaffold to a real, static export — a Python-side dump of one representative outage session (ground truth, aided, dead-reckoned trajectory, calibrated confidence radius per timestep, **real lat/lon**, not just local east/north) — consumed as a build-time or fetched static JSON file, per Step 6's no-backend contract.

**[FIX-16]** Before choosing which session to export: confirm what dataset it actually comes from and what it actually contains. `PLAN.md` states plainly that **all evaluation uses synthetic masking — the dataset's real GPS dropouts have no ground truth and exist only as exclusions** (i.e. there is no session with a *real* tunnel outage and real ground truth through it; every scored outage is a synthetic mask over otherwise-continuous data). Separately, the WhONet benchmark referenced elsewhere in `PLAN.md` is England-only and explicitly *not* reproduced by this project — confirm the exported session is genuinely from IO-VNBD (this project's actual dataset) and not accidentally conflated with WhONet reference numbers. **Label the exported session's outage as a synthetic mask in the UI, honestly** — do not imply a real tunnel dropout where the ground truth is itself synthetic.

### Task

1. Add an export script in `python/scripts/` (check `summarise_results.py` first — it may already emit per-timestep trajectories) producing ground-truth/aided/dead-reckoned trajectory + calibrated confidence + **real lat/lon** for one representative synthetically-masked outage from IO-VNBD, plus clear metadata marking the outage as synthetic.
2. Wire the frontend's state machine to real timestamps/positions/confidence from that export, replacing `mulberry32` simulation for this view.
3. Preserve deterministic replay if practical.
4. Do not fabricate any number without a real per-session equivalent — keep static reference annotations (like the demo's AVNet citation) exactly as static, not pretend-live.

### Verification

```
cd frontend && npm run build && npm run dev
```

### Exit criteria

- Web MVP renders one real, previously-computed outage session end-to-end, honestly labeled as a synthetic mask, with real lat/lon.
- Every displayed number traces to `eval/results/` or the export — documented in `frontend/README.md`.

### Rollback

Revert branch.

---

## Step 8 — Web: real-world map basemap

**Model tier:** default (Sonnet), tile-source choice via `search-first`.
**Depends on:** Step 7. **Parallel with:** Step 3, Step 11.
**Branch:** `feat/web-map-basemap`

### Context brief

Unlike Android, the web MVP has no offline/no-network requirement to solve — it's a hosted app. The decision here is cost/licensing, not offline capability. Same anti-vendor-gate positioning as Android: prefer **MapLibre GL JS** with a free-tier or self-hosted vector-tile source over Mapbox GL JS (paid) or the billing-gated Google Maps JS API.

**[FIX-16, continued]** Since the exported session's route may not correspond to any real tunnel (see Step 7), this step's job is to place the route at its **correct real-world coordinates**, honestly — not to manufacture a "the tunnel is really there" narrative that the data doesn't support.

### Task

1. `search-first` to confirm current MapLibre GL JS + a suitable free/self-hosted tile source (e.g. MapTiler free tier, or a self-hosted PMTiles extract reusing Step 3's tile-build tooling for consistency).
2. Render the real georeferenced route from Step 7's export on the map; overlay the orb/chevron/trails at the correct map position, either via a custom-layer/Three.js integration or a synchronized 2D-map + separate-viewport approach — document the choice and trade-offs in `frontend/README.md`.
3. Verify the route appears at its actual real-world location — a coordinate-transform bug here would produce a good-looking but geographically fake map, which violates the spirit of constraint 2 even though it's visual rather than a written claim.
4. Display attribution.

### Verification

```
cd frontend && npm run build && npm run dev
```

### Exit criteria

- Web MVP shows the replayed route over real map tiles, correctly georeferenced, honestly labeling the outage as synthetic.
- Attribution displayed.

### Rollback

Revert branch; Step 7's non-mapped view remains available as a fallback.

---

## Step 9 — Web: UX polish + deployment

**Model tier:** default (Sonnet).
**Depends on:** Step 8. **Parallel with:** Step 4.
**Branch:** `feat/web-ux-deploy`

### Task

1. Apply `ui-ux-pro-max` for a cohesive design system matching Android's `Palette` and the demo's colour language (cyan/amber/magenta) exactly — check contrast against real map imagery too, not just flat backgrounds.
2. Playwright E2E tests (via `e2e-testing` skill) for the critical flow: load session → LOCKED → blackout → REACQUIRING with no visible jump.
3. Deploy to a real static/edge host (Vercel/Netlify) — no backend to deploy, per Step 6's no-API-layer decision. Document the live URL.
4. `deployment-patterns` skill for hosting/CI config. If a keyed tile provider was chosen in Step 8, inject the key via environment config at build/deploy time — never commit it.

### Verification

```
cd frontend && npm run build && npx playwright test
```

### Exit criteria

- E2E suite passes; app live at a real URL; colour language matches Android/demo; no secret committed.

### Rollback

Revert branch; roll back host deployment if needed.

---

## Step 10 — Pitch deck: competition research

**Model tier:** default (Sonnet).
**Depends on:** Step 0. **Parallel with:** Step 1, Step 6.
**Branch:** none needed (research doc, direct commit or small PR)

### Task

1. `market-research` skill, scoped narrowly to SIH-style deck structure/judging norms — not re-verifying technical claims.
2. Produce `research/SIH26168-pitch-deck-findings.md`, cited, following the existing docs' discipline.
3. Cross-reference `PLAN.md` §1 "Pitch framing"/"What NOT to claim" and risk #7 (overclaiming) — reinforce, don't contradict.

### Exit criteria

`research/SIH26168-pitch-deck-findings.md` exists with cited sources and a clear structure recommendation.

### Rollback

Delete the file/revert the commit.

---

## Step 11 — Pitch deck: build the deck

**Model tier:** default (Sonnet).
**Depends on:** Step 10. **Parallel with:** Step 3, Step 8.
**Branch:** none needed if delivered as an Artifact; otherwise `feat/pitch-deck`

### Context brief

Every claim traces to `eval/results/`, `PLAN.md` (post Step 0 correction), or the research docs. Use **1.7x-43.0x** (FIX-1), not any other figure.

**[FIX-3]** If `demo/gnss-demo.html` screenshots are used as placeholders (real app/web screenshots preferred once Steps 5/9 land): the demo's on-screen readouts include `ESTIMATOR InEKF 21-STATE · SE₂(3)` and `LOSS CAUSE · BLOCKAGE · C/N₀ ↓ AGC =`. Per `PLAN.md`, the 21-state strapdown is **not used** (the deployed MVP is a 5-state 2D kinematic filter) and loss-cause attribution is **blocked** (no C/N₀/AGC in the dataset). **Any demo screenshot used in the deck must be captioned "simulated UI concept," and the InEKF-21-state / loss-cause-AGC / NavIC-in-fix panels must be cropped or annotated "not built (PLAN.md §4)."** Putting unbuilt-feature UI in front of judges unlabeled is exactly the overclaim `PLAN.md` risk #7 warns against.

### Task

1. `frontend-slides` skill for an animation-rich deck, structured per Step 10's findings.
2. Content, each item sourced: problem framing (`PLAN.md` §1), architecture (§2.1, simplified), measured results (the corrected 1.7x-43.0x table + calibration story from `eval/results/`), honest limitations (drift-vs-AVNet gap, speed staleness — `PLAN.md`'s "Remaining Phase 1 gap"), live demo footage (real app/web screenshots preferred; demo screenshots captioned per the rule above), explicit avoidance of the four killed novelty claims (`PLAN.md` §1).
3. `dataviz` skill for any chart.

### Exit criteria

- Complete deck; zero claims beyond `eval/results/`/`PLAN.md`/research docs; correct 1.7x-43.0x figure; any demo screenshot properly captioned/cropped per FIX-3; the four killed claims absent.

### Rollback

Standalone artifact; discard/rebuild if Step 13 finds issues.

---

## Step 12 — Security review + release signing hygiene + on-device release validation

**Model tier:** default (Sonnet) for implementation, security-reviewer agent for the review.
**Depends on:** Step 5, Step 9. **Parallel with:** none.
**Branch:** `feat/release-hygiene`

### Context brief

`android/app/build.gradle.kts:33`: release build type is signed with the **debug keystore**. Fine for `adb`-installed demo builds, not for any claim of a shippable product.

**[FIX-11]** Signing and verifying the release APK is not the same as validating it runs correctly. R8 minification + resource shrinking (`isMinifyEnabled`/`isShrinkResources`, both true) can strip JNI-referenced classes or provider assets that Filament/MapLibre need and that the debug build (Step 5's validation target) never exercises. **This step must install and actually run the signed release build on the connected device**, not stop at `apksigner verify`.

### Task

1. Confirm the Step 0 Play Store-scope answer; if out of scope, explicitly document "shippable" as "a properly-signed release build installable via direct APK / internal testing track."
2. Generate a real release keystore (git-ignored, `local.properties`/build-time-injected secrets per the Kotlin security rules already in force). Wire `build.gradle.kts`'s `release` block to it.
3. `security-review` skill / `security-reviewer` agent across Android (permissions — confirm the 3D/map work added none beyond what's justified, and specifically confirm **no `INTERNET` permission was added** per the bundled-tiles decision; data handling; `FileProvider` usage) and web (Step 6's static-file-only architecture should mean there's no API surface to review, which is itself worth confirming rather than assuming).
4. **[FIX-11]** `./gradlew :app:assembleRelease` with the real keystore, install on the connected device, run one full LOCKED → simulated BLACKOUT → REACQUIRING cycle, confirm the orb, map, and all readouts render correctly under R8/shrink-resources — i.e. confirm Filament/MapLibre's consumer ProGuard rules are actually present and effective. If anything renders incorrectly only in the release build, add the necessary keep rules and re-verify.
5. Confirm Step 5's on-device debug-build validation surfaced no blocking finding (rendering starving the sensor pipeline); if it did, this step is blocked until resolved.
6. Record final APK size against the Step 1 ceiling and the session's original 2,226,384-byte baseline.

### Verification

```
./gradlew :app:assembleRelease
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
adb install -r app/build/outputs/apk/release/app-release.apk
# Manual on-device: full LOCKED -> BLACKOUT -> REACQUIRING cycle on the RELEASE build.
```

### Exit criteria

- Release APK signed with a real key, secrets not committed.
- Release build **installed and run on-device**, full state cycle confirmed working under R8/shrink-resources.
- No `INTERNET` permission present (unless a later decision explicitly changed the bundled-tiles approach, in which case this is itself a flagged finding).
- Security review complete for both surfaces; final APK size documented.

### Rollback

Revert branch; the debug-signed config remains the documented-gap fallback until redone.

---

## Step 13 — Final cross-surface integration verify

**Model tier:** default (Sonnet), code-reviewer agent pass.
**Depends on:** Step 11, Step 12. **Parallel with:** none.
**Branch:** none — verifies `master` post-merge.

### Task

1. Full verification: `./gradlew :shadownav-core:test :app:testDebugUnitTest` (+ the release on-device cycle already done in Step 12), `cd frontend && npm run build && npx playwright test`, manual deck review.
2. `/code-review` across all changed files, Steps 0-12.
3. Confirm every non-negotiable constraint still holds, including the ones added in this revision: bundled tiles / no `INTERNET` permission, no Filament-map GL compositing anywhere, `PLAN.md`/`README.md` numeric consistency (FIX-1, FIX-20).
4. Update `README.md`'s status table and `PLAN.md`'s Phase E/Phase 4 sections.

### Exit criteria

All three deliverables complete, cross-checked, status docs accurate.

### Rollback

Fix forward on a small branch; revert a specific step's PR only if it's the clear root cause of an integration conflict.

---

## Execution note on branching

Merge each step's PR to `master` as it completes and passes its own verification (not one long-lived integration branch) — this is why Step 5 and Step 12 validate real, already-integrated `master` state. Use `/verify` after each merge. Rollback for any already-merged step means reverting that merge commit on `master`, not "closing a PR without merging."

## Plan mutation protocol

- **Split:** Step 6 is pre-split into 6a/6b. If Step 2 or Step 3 still prove too large, split along engine-setup vs. per-scene-content and use `2a`/`2b`/`3a`/`3b` suffixes.
- **Reorder:** the web track (6-9) and Android track (1-5) have no hard dependency on each other past Step 0 and can swap priority if the connected device becomes unavailable.
- **Abandon:** Step 1's on-device smoke benchmark (not Step 5) is the first real gate — if the engine can't run acceptably even reduced, abandon Steps 2-5's 3D framing there, fall back to the demo's Canvas2D-equivalent techniques natively (still a real upgrade, just not 3D), and document in `PLAN.md`'s risk register. If Step 3's bundled-tile approach proves unworkable (storage, tooling), fall back to an abstract-plane 3D scene (what v1 of this plan called "Step 3" before the merge) rather than a basemap that silently fails.

## Review changelog

v1 of this plan was reviewed by an Opus-tier adversarial pass on 2026-09-05 and returned "NEEDS FIXES FIRST" with 4 CRITICAL and 18 MAJOR findings plus 5 MINOR. All CRITICAL and MAJOR findings are addressed above (tagged **[FIX-n]** at point of resolution); MINOR findings (stale byte-for-byte wording, the `conformalLambda` coupling note, the Compose-decision-as-explicit-task note, the Play-Store-question timing, and the mangled ASCII dependency diagram) are folded into Step 0/1/3's context and this revision's redrawn diagram. The reviewer separately confirmed as solid and unchanged: file-level parallel-safety across all steps, every original code citation (line numbers in `TrackView.kt`, `MainActivity.kt`, `libs.versions.toml`, commit `a5ac728`), the load-bearing 2.146/conformal-λ math, and the basemap-vs-map-matching distinction.
