# ShadowNav — Android

Live smartphone dead reckoning through GNSS blackouts. Two modules:

```
shadownav-core/   pure Kotlin/JVM — the estimator. No Android dependency.
app/              Android — sensor capture, GNSS, UI.
```

## Build

```bash
export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
./gradlew :shadownav-core:test      # the parity suite — run this first
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`local.properties` needs `sdk.dir` with **forward slashes**; a Java properties
file treats `\U` in a Windows path as an escape and the build fails with an
unhelpful `Invalid file path`.

| | |
|---|---|
| minSdk | **29** |
| targetSdk / compileSdk | 35 |
| Java/Kotlin target | 17 |
| Permissions | `ACCESS_FINE_LOCATION` only |
| APK size | **2.2 MB** release (R8 + resource shrinking), 12 MB debug |

API 29 is set by the feature we actually want, not by habit:
`GnssStatus.CONSTELLATION_IRNSS` — the NavIC enumeration — lands at 29. AGC
needs 33 and is treated as opportunistic, never required.

## Features

| | |
|---|---|
| **Simulate tunnel** | Press and hold to discard GNSS fixes while keeping satellite telemetry live. Turns any road into a repeatable blackout test, which a real tunnel is not. Held rather than toggled so a demo cannot be left switched on by accident, silently invalidating everything after it. |
| **Trip recording** | Writes a 26-column CSV and shares it. This is what closes the loop: the app has no ground truth, the offline pipeline has all the metrics, and until now nothing connected them. Column names match `shadownav/data/schema.py` where they overlap. |
| **Trip summary** | Distance, duration, seconds spent dead reckoning, longest unaided run. |
| **Calibrated confidence** | A 90% containment radius and a bar that turns amber then magenta, using the val-fitted conformal factors — never the raw covariance, which understates by 15–22×. |
| **Live diagnostics** | Measured IMU rate, satellites in fix, C/N0, NavIC, AGC state, alignment quality, and gate statistics. |
| **Stationary hold** | Zero-velocity update when the IMU says the vehicle is parked. |

## Why `shadownav-core` has no Android dependency

Because it has to be *provably* identical to the Python implementation, and that
proof should be an ordinary JVM unit test rather than something needing a device
or emulator.

`shared/README.md` makes this a requirement: *"Verify the Kotlin path reproduces
the Python path numerically on a fixed replay before trusting any on-device
number."* The reason is that the app has no ground truth. A sign error, a
transposed Jacobian or a wrong angle wrap produces a trajectory that looks
entirely plausible on screen and is wrong.

`ParityTest` replays nine golden cases exported from Python and requires
agreement to **1e-9**:

| case | covers |
|---|---|
| `geo` | WGS84 → ENU, curvature radii, course from a held track |
| `propagate` | 90 propagation steps, state and covariance |
| `propagate_accel` | propagation with forward acceleration supplied |
| `updates` | position, speed, course, centripetal, Ackermann in sequence |
| `gate_escape` | consecutive rejection triggers a re-anchor |
| `ackermann` | curvature and friction bounds across six operating points |
| `blend` | the critically damped re-acquisition spring |
| `alignment` | device-to-car rotation and its quality score |
| `features` | the six rotation-invariant channels |

Regenerate them from `python/`:

```bash
PYTHONPATH=. python scripts/export_golden.py
```

If a port changes and the vectors do not, the test fails — which is the point.

## What the app measures, and why the readouts are what they are

**IMU rate is the headline diagnostic, not a footnote.** Every negative result
in the offline work traces to IO-VNBD logging at 10 Hz: the 21-state strapdown
diverged to 5×10⁴ m/s, the centripetal observation hurt rather than helped, and
the learned speed head barely beat a constant — because road and engine
vibration lives above 5 Hz and is aliased away at 10 Hz.

So `SensorCapture` requests the fastest rate and then **measures what it
actually gets**, alongside the largest inter-sample gap. A phone that advertises
`SENSOR_DELAY_FASTEST` may still deliver 50 Hz, and a number produced on a given
phone is only meaningful next to the rate it was produced at.

**The confidence ring is calibrated, not raw.** Offline, the filter's own
nominal 90% ellipses contained **17%** of errors. `assets/conformal.json` ships
the per-horizon inflation factors fitted on the val fold; the ring is
`λ · 2.146 · σ`. Drawing the raw covariance would understate uncertainty by
15–22×, which is worse than showing nothing.

**NavIC is instrumentation.** The panel enumerates IRNSS satellites and how many
entered the fix. A phone typically sees 1–3 against the 4 needed. Never present
this as a positioning improvement.

**AGC status is stated honestly in three states** — unavailable below API 33,
supported-but-not-yet-reported, or an actual value. Google's own documentation
says AGC is not reported when a signal is too weak to acquire, which is exactly
inside a tunnel. `agcEverSeen` distinguishes "this device cannot" from "this
device can but is currently silent", and that distinction is the difference
between a claim that survives a judge's question and one that does not.

## On-device results — moto g64 5G, Android 15

First hardware run, 2026-09-05. Device: Motorola moto g64 5G, MediaTek MT6855,
8 cores, Android 15 (API 35), arm64-v8a. A budget-class phone, which is the
target.

| | |
|---|---|
| IMU | InvenSense **ICM-456xy** |
| **Measured accelerometer rate** | **401 Hz** (device advertises 400) |
| Max inter-sample gap | 2 ms at rest, 22 ms across an app restart |
| Crashes | none after the two fixes below |
| App state | runs, renders, reports honestly |

### The number that matters

**401 Hz measured, against the 10 Hz of IO-VNBD.** That is a factor of 40, and
it is the direct test of this project's central claim.

Every negative result in the offline work — the 21-state strapdown diverging to
5×10⁴ m/s, `L_cent` hurting rather than helping, the learned speed head barely
beating a constant — was attributed to 10 Hz aliasing away the vibration
signature that lives above 5 Hz. That attribution was an argument. It is now
testable on hardware that delivers 40× the bandwidth, and re-running those three
ablations here is the highest-value experiment left in the project.

### Two bugs that only hardware could find

**`SecurityException: To use the sampling rate of 0 microseconds, app needs to
declare HIGH_SAMPLING_RATE_SENSORS`.** Since Android 12, requesting above
200 Hz needs that permission, and `SENSOR_DELAY_FASTEST` (0 µs) qualifies. It
**throws rather than degrading**, so the app crashed on launch. Now declared,
and `SensorCapture` falls back to `SENSOR_DELAY_GAME` and raises a
`[RATE DEGRADED]` flag if it is ever refused — a navigation app that dies
because it could not have its preferred rate is worse than one that runs slower
and says so.

**The UI claimed `AIDED` with no fix.** Before the first fix the filter has not
started, so the state machine has not run and still reads its initial value.
Displaying that asserts GNSS aiding while there are zero satellites, which is
precisely the confident-and-wrong display this project exists to avoid. It now
shows `ACQUIRING` in grey until a fix exists. The mode label also rendered
underneath the status bar; window insets are applied now.

### A third bug: collection stopped when the app left the screen

Sensor capture and the filter lived in the Activity. The moment the user
switched apps, Android froze the process and collection stopped dead after two
minutes. For something whose entire purpose is surviving a tunnel, losing state
because the screen turned off is not a limitation, it is a defect.

`NavigationService` is now a foreground service holding the capture and the
engine; the Activity binds to it purely for display and unbinds without stopping
it. Verified on device: with the launcher in the foreground, the service reports
`isForeground=true types=0x00000008` and logging continues at 401 Hz.

This is also why a notification appears. It is the platform's required price for
background location, and it doubles as a live readout visible without unlocking.

### A fourth bug: dead reckoning away while parked

With location finally enabled, the phone took a weak 3-satellite indoor fix
that reported **4.1 m/s**, lost it, and then dead-reckoned at 4.1 m/s
indefinitely while sitting on a desk. σ grew honestly from 24 m to 33 m, but
the position ran away. With speed held and no GNSS, nothing could contradict it.

The IMU knew all along. `StationaryDetector` watches specific-force variance,
its deviation from g, angular rate, and — critically — the **tilt** of the mean
specific force against a reference vertical. Tilt is what catches horizontal
acceleration: a 1.5 m/s² forward push lifts |a| only from 9.807 to 9.921, which
magnitude alone cannot see, but tilts the apparent vertical by 8.7°, which is
unmistakable. When stationary it applies a zero-speed update at σ = 0.05.

It took two attempts to get right on hardware, and both failures were invisible
from its boolean output, which is why it now exposes its internals:

1. It ran *after* `val f = ekf ?: return`, so it never executed before the first
   GNSS fix — exactly when a stale speed does the damage.
2. The tilt reference was hardcoded to `(0,0,1)` until a fix arrived, so unless
   the phone lay perfectly flat every sample was rejected. Gravity comes from
   the IMU alone and is now bootstrapped from it.

Verified on device, phone at rest:

```
stat=false std=0.018 mag=9.862 gyr=0.0127 tilt=0.0018 blk=none held=1.4
stat=true  std=0.012 mag=9.859 gyr=0.0038 tilt=0.0015 blk=none held=5.4
```

Every condition passes with margin, and the 1.5 s dwell is respected.

### An app icon

`ic_launcher` is a navigation chevron half-eclipsed: cyan for the GNSS-aided
half, magenta for the dead-reckoning half, with the amber containment ring
beneath. The name refers to GPS shadow, so the mark is a heading arrow with a
shadow across it, in the same colour language the app and the demo already use
for those states.

### Not yet measured

No GNSS fix was obtained — the test was indoors, `sats 0/0`. Everything
downstream of the first fix is therefore **untested on hardware**: filter
initialisation, the alignment bootstrap, the blackout FSM, blend-back, and the
NavIC panel. AGC reported `supported by API but not yet reported`, which is the
honest third state and cannot be resolved without sky view.

The remaining Phase E numbers — latency, battery drain, thermal behaviour over a
sustained drive — still do not exist.

## Deliberate differences from the offline pipeline

| | offline (10 Hz dataset) | on device |
|---|---|---|
| Estimator | 5-state kinematic | same, ported |
| Forward-acceleration speed | measured to hurt, off | **still off** — re-run the ablation before enabling |
| Centripetal observation | measured to hurt, off | **still off** — same reason |
| Ackermann bounds | on, marginal | on |
| Learned speed head | trained, opt-in | not yet wired (see below) |

Nothing was enabled on device merely because more data is available. Each is
gated on re-running its ablation at the rate the phone actually delivers.

## Not yet done

- **The learned speed head is not wired in.** It is trained, calibrated and
  documented in `shared/`, but it is off by default in the offline pipeline too:
  it helps at 30–120 s and hurts at 180 s, carrying a bias that is a driver-shift
  artefact rather than a model property. Wiring an unconditional learned
  correction that helps sometimes and hurts otherwise would repeat a failure a
  competitor has already published. The indicated fix is a confidence gate.
  Inference path when it lands: export ONNX (`torch.onnx.export` works here;
  TensorFlow is not installed so TFLite conversion is not available locally) and
  add ONNX Runtime Mobile. NNAPI is deprecated as of Android 15 and inconsistent
  on low-end SoCs, so INT8 on CPU with XNNPACK is the target.
- **No on-device measurement yet.** Latency, battery drain and thermal
  behaviour are the Phase E numbers that matter and none of them exist. The
  2.36 ms / 3.71 ms p95 figure in `eval/results/inference_latency.json` is a
  desktop single-thread proxy and is labelled as such everywhere it appears.
- **No drive log or replay export.** Needed before any on-device claim can be
  checked against the offline pipeline.
- **The 21-state strapdown is not used**, even though the phone's higher rate is
  exactly the condition under which it should work. That is the first
  experiment to run once real high-rate logs exist.
