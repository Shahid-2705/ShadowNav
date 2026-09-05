# ShadowNav — Web MVP

Blueprint Steps 6 (scaffold + renderer port) and 7 (real data wiring) from
`plans/shadownav-3d-mvp-web-deck.md`. Reuses `demo/gnss-demo.html`'s visual
language and rendering techniques, componentized into a real React/Three.js
app, wired to a real replayed outage session instead of the demo's seeded
simulation.

## Stack decision (Step 6a)

**Vite + React 19 + TypeScript + Three.js.** Confirmed via live npm registry
lookups on 2026-09-06 (do not assume these are still current later):
`vite@8.2.2`, `three@0.185.1`, `react@19.2.8`, `typescript@7.0.2`.

**Actually shipped: Vite 6.4.3, not 8.2.2.** Vite 7 and 8 both require
`node ^20.19.0 || >=22.12.0` (their new default bundler, Rolldown, ships
native platform binaries that fail to load below that). This dev machine
has Node 20.17.0 installed system-wide with no version manager available,
and a clean `node_modules`/`package-lock.json` reinstall did not fix it
(ruling out the "known npm optional-dependency bug" the error message
itself suggests) -- it is a genuine engine-version gap, not a transient
install issue. Vite 6.4.3 (the latest 6.x, still on the stable Rollup/esbuild
bundler) supports any Node 20.x and was verified to build cleanly.
`@vitejs/plugin-react` is correspondingly pinned to `4.7.0` (the last line
compatible with Vite 6; the `6.x` plugin-react line requires Vite 8).
**Revisit this pin once the dev/build environment has Node >=20.19.**

Three.js was chosen over a lighter vanilla+Vite port because the demo's
WebGL concepts (icosphere geometry, bloom, a lit shard material) map
directly onto Three.js's own primitives (`BufferGeometry`,
`UnrealBloomPass`, `MeshStandardMaterial`) with a maintained library behind
the parts that don't need to be hand-rolled twice.

## No backend, ever (FIX-18)

This app is **static files only** -- no server, no API route, no runtime
backend. The only "dynamic" data is `public/data/session.json`, a file
generated once by `python/scripts/export_web_session.py` and fetched at
load time like any other static asset. There is deliberately no
input-validation/rate-limiting/auth surface to secure later, because there
is no surface.

## What's real vs. what's a deliberate placeholder

| Piece | Status |
|---|---|
| Icosphere shard-fracture geometry (`src/three/icosphereShards.ts`) | **Faithful port** of `demo/gnss-demo.html`'s `buildIcosphere`/`clusterFaces`/`buildShardSet`/`packShards` -- same seeded region-growing, same closed-form impulse/damping/gravity trajectory as a function of the fracture clock `tau`. |
| Bloom (`src/three/orbScene.ts`) | Three.js's own `UnrealBloomPass`, not the demo's hand-rolled two-pass separable blur -- same technique (bright-pass + blur + additive composite), a maintained implementation instead of a line-for-line GLSL port. |
| Shard shading | Simplified to `MeshStandardMaterial` with emissive colour/intensity driven by state, not the demo's custom seam/rim/core GLSL shader. The state-colour language (cyan/amber/magenta, from `src/state/palette.ts`) matches Android's `Ui.kt` `Palette` exactly. |
| Tier system (HIGH/LOW) | Ported: HIGH = subdiv 2 / 84 shards, LOW = subdiv 1 / 36 shards, auto-degrade after 45 of 60 frames over 22ms, matching `demo/README.md`'s own rule -- only swaps the shard set when `tau` is near zero (orb whole), same reasoning as the demo. |
| Canvas2D fallback | **Reduced scope**, not a port: if `OrbScene`'s `WebGLRenderer` construction throws, the orb canvas is left blank rather than the demo's full painter-sorted 2D re-implementation (shards, motes, route, markers). The route panel is unaffected -- it is already a plain 2D canvas, not WebGL, so it works regardless. Closing this gap (a real Canvas2D orb fallback) is a follow-on item, not silently dropped. |
| Route/trail/ring/vehicle (`src/components/RoutePanel.tsx`) | Real, driven by the real exported session, auto-scaled local-metre projection (not yet a real map -- that is Step 8, not done here). |
| Real-world map basemap | **Not done.** Blueprint Step 8. The route panel explicitly labels itself "no basemap yet" on-screen so this isn't mistaken for a finished feature. |
| Data | **Real**, not simulated -- see below. |

## Data contract (Step 7)

`python/scripts/export_web_session.py` reuses `run_mvp.py`'s exact
load -> mask -> run pattern (same split, same seed) -- not a second,
divergent pipeline -- and exports one representative outage window
per-timestep instead of reducing it to summary statistics.

Run to regenerate:

```bash
cd python
PYTHONPATH=. python scripts/export_web_session.py --horizon 60 --fold test
```

Produced this session (2026-09-06): **`S-M#0`, test fold, 1051 rows, a 60s
synthetic outage starting at t=35.0s, 128.6m travelled during the outage**,
written to `frontend/public/data/session.json` (198,314 bytes).

**Every number traces to a real source:**

| Field | Source |
|---|---|
| `estLat`/`estLon` | `shadownav.pipeline_kinematic.run()`'s `east_m`/`north_m`, inverted back to lat/lon via the exact inverse of `geo.py`'s `lla_to_enu` (same WGS84 constants, `geo.py` has no built-in inverse so one was added in the export script). |
| `truthLat`/`truthLon` | The sequence's own recorded `gps_lat_deg`/`gps_lon_deg` -- i.e. real GPS fixes, held between updates exactly the way the source CSV holds them (`python/README.md`'s documented ~9s fix period). |
| `radius90m` | `sqrt(0.5*(cov_xy[0,0]+cov_xy[1,1])) * conformalLambda * 2.146` -- the *exact* same formula `MainActivity.render()` and `TrackView.kt` use on Android, using the same `shared/conformal.json` factor for the 60s horizon (17.08). Never a different, web-only convention. |
| `mode` | `Trajectory.mode` from the real filter run, mapped to the shared six-state vocabulary in `src/state/signalState.ts` (matching `android/.../UiSignalState.kt` by name). |

**Honesty label (FIX-16):** `PLAN.md` documents that all evaluation uses
synthetic masking -- the dataset's real GPS dropouts have no ground truth
and are excluded entirely. This export's outage is a synthetic mask over
otherwise-continuous driving, not a real tunnel dropout. The exported JSON
carries `"synthetic": true` and an explanatory `"note"` field, and the
`Dashboard` component renders that note as a visible banner -- not a
buried disclaimer.

## Running

```bash
npm install
npm run build   # tsc -b && vite build -- verified working 2026-09-06
npm run dev
```

## Open items for later steps

- Step 8: real MapLibre GL JS basemap under the route panel (currently a
  plain 2D canvas with an auto-scaled local projection, explicitly labelled
  "no basemap yet" on-screen).
- Step 9: Playwright E2E test for the LOCKED -> outage -> REACQUIRING flow,
  deployment to a real static host.
- A real Canvas2D fallback for the orb (see table above) -- currently the
  orb canvas goes blank rather than degrading to a 2D redraw if WebGL is
  unavailable; the route panel and dashboard remain fully functional either
  way since they don't depend on WebGL.
- Bundle size: the production build is 739 kB (200 kB gzip), mostly
  Three.js -- fine for now, but `build.rollupOptions.output.manualChunks`
  or dynamic `import()` would help once this is deployed for real (Step 9).
