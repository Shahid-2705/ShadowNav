# ShadowNav — Android

Live smartphone dead reckoning through GNSS blackouts. Two modules:

```
shadownav-core/   pure Kotlin/JVM — the estimator. No Android dependency.
app/              Android — sensor capture, GNSS, UI.
```

## Build

```bash
export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
gradle :shadownav-core:test      # the parity suite — run this first
gradle :app:assembleDebug
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
