# ShadowNav — Python pipeline

Data, evaluation and estimator code for SIH26168. See [../PLAN.md](../PLAN.md)
for the project plan and [../research/](../research/) for the technical dossiers.

## Setup

```bash
cd python
pip install -e ".[dev,train,plot]"
python -m shadownav.data.fetch          # ~202 MB, gitignored
pytest
```

`data/` is gitignored. IO-VNBD is CC BY 4.0 via its *Data in Brief* version
(PMC7907232); we fetch it, we do not redistribute it. Attribute Onyekpe, Palade,
Kanarachos & Szkolnik (arXiv:2005.01701) in any writeup.

## Layout

```
shadownav/
  data/       IO-VNBD loading, schema resolution, defect repair, fetching
  evaluation/ outage masking, metrics, the published split, conformal calibration
  baselines/  naive strapdown INS — the drift floor
  filter/     21-state strapdown EKF, 5-state kinematic EKF, alignment, GNSS FSM
  models/     invariant features, CNN+GRU speed net, inference adapter
  utils/      determinism
  geo.py      WGS84 -> local ENU
  pipeline_kinematic.py   the deployed end-to-end estimator
scripts/
  audit_gps_rate.py       measures the real GPS fix rate
  run_baseline.py         -> eval/results/baseline_naive.json
  run_mvp.py              -> eval/results/kinematic*.json
  train_speednet.py       -> shared/speednet.pt
  calibrate_confidence.py -> eval/results/conformal_calibration.json
```

## Reproducing the numbers

```bash
PYTHONPATH=. python scripts/audit_gps_rate.py        # dataset fix-rate audit
PYTHONPATH=. python scripts/run_baseline.py          # the drift floor
PYTHONPATH=. python scripts/run_mvp.py               # the MVP estimator
PYTHONPATH=. python scripts/train_speednet.py --ablate   # speed net + ablation
PYTHONPATH=. python scripts/run_mvp.py --speednet    # MVP with the learned front end
PYTHONPATH=. python scripts/calibrate_confidence.py  # conformal inflation
```

Both are seeded (`shadownav.utils.seed.DEFAULT_SEED = 20260905`) and reproduce
exactly. Nothing in this project draws from module-level `np.random` state.

## Findings that changed the plan

Auditing all 72 S-side files surfaced four things the research dossiers did not
record. Each is implemented as a defended behaviour with a regression test, so
removing the mitigation fails the suite rather than silently corrupting results.

### 1. GPS updates every ~9 s, not 1 Hz

Track H and [PLAN.md:149](../PLAN.md#L149) state 10 Hz sampling with a 1 Hz GPS
update, i.e. fixes repeating in blocks of ~10. Measured across 29.7 h and
1,065,249 rows:

| | Track H | Measured |
|---|---|---|
| IMU sample rate | 10 Hz | **10.00 Hz** ✓ |
| GPS fix period | 1 s | **9.0 s** (median; range 1–13 s) |
| Rows per fix | ~10 | **89.4** |
| Sessions consistent with 1 Hz | all | **3 / 79** |
| Vehicle travel between fixes | ~2.8 m | **27.1 m** (max 70 m) |

There are only **14,067 real position observations in the whole dataset**. This
is not a detail — it sets what the data can and cannot answer:

* a 10 s outage suppresses roughly one real fix, a 30 s outage roughly three;
* scoring at 10 Hz against interpolated truth would report interpolation error
  as estimator error, and between fixes 27 m apart on a curve that is metres.

So metrics are evaluated **only at rows carrying a real fix**, each result
reports the actual elapsed time (which can exceed the requested horizon by up to
one fix period), and `truth_gap_m` is reported alongside every number.

Fix detection keys on **latitude and longitude only**, and getting that wrong
is possible in both directions. Latitude alone reports the rate wrongly by an
order of magnitude: on a near-east/west drive it is constant to 6 decimal places
for scores of rows while longitude advances at every fix. The whole GPS tuple is
equally wrong the other way — course and reported accuracy jitter every sample
while the vehicle is stationary, so S-Y1 reported 785 "fixes", most of them at
zero speed with the vehicle not moving, and the filter believed it was being
corrected when it was not.

### 2. Excel date corruption of the satellite column

**12 of 72 files** contain values like `Dec-14`, `Nov-16`, `10-Dec` in
`GPS SATELLITES IN RANGE` — Excel's date autocorrect applied to `"12 / 14"`,
`"11 / 16"`, `"10 / 12"`. Somebody opened the CSVs in Excel and re-saved them.
2,118 rows affected; S-Vta28 is 19% corrupted.

The corruption is selective in the worst possible way: Excel only converts a
value it can read as a date, which needs the first number ≤ 12. So it destroys
exactly the rows where **fewer than 13 satellites were in the fix** — the
degraded-GNSS rows this project exists to handle. Dropping them would bias the
dataset away from the condition under test.

The transform is exactly invertible, and all 48 distinct corrupted forms present
in the dataset invert to `used <= visible` — the independent invariant that says
the inversion is right.

### 3. Concatenated recording sessions

**5 files** contain a point where `TIME SINCE START` resets toward zero while
wall-clock `DATE` continues forward. In S-S2 the clock jumps 186311 ms → 10 ms
while the date advances 12:06:58.041 → 12:06:59.249. These are separate
AndroSensor recordings concatenated into one CSV.

They are split, not stitched: integrating across such a boundary injects a
fabricated 186-second gap into the trajectory. 72 files yield 79 sessions.

### 4. Duplicate timestamp rows

**7 files** repeat rows at an identical timestamp; S-Vtb1 has 5,456 such pairs
across 32,459 rows (17%). 5,370 of 5,456 are byte-identical duplicates of their
predecessor, so deduplication is safe and discards no independent sample.

### Also: two header hazards not in Track H

CRLF line endings, and an internal trailing space inside `ORIENTATION (Roll )`.
Column resolution matches on ASCII token signatures rather than exact strings or
position, so unit-symbol encoding damage cannot break it and an inserted column
cannot silently shift gyroscope data into accelerometer fields.

## The naive baseline, and one thing it taught us

`baselines/naive.py` is an unaided strapdown INS: attitude from gyroscope
integration, gravity removed analytically, acceleration double-integrated. No
ZUPT, no nonholonomic constraint, no learned correction, no map. Accelerometer
and gyroscope only — the dataset's `GRAVITY`, `MAGNETIC FIELD` and `ORIENTATION`
columns are fused outputs of the phone's own sensor stack, and using them would
quietly import a magnetometer into a system that claims not to have one.

Building it surfaced a failure mode worth recording. Levelling on the *mean*
specific force assumes the only acceleration is gravity. On a turning vehicle it
is not: a centripetal 1.04 m/s² tilts the estimated vertical by 6°, which
mis-projects gravity by `g·sin(6°) = 1.03 m/s²` of pure horizontal error.
Double-integrated over 20 s that is **206 m** — larger than the distance
travelled, and it dominates every other error source. `select_alignment_window`
therefore scores candidate windows by how close their mean specific force is to
g plus their gyroscope energy, and picks the quietest moment available.

This is the same observability problem [PLAN.md:191](../PLAN.md#L191) flags for
calibration, in a different guise, and it is a concrete argument for the
opportunistic-calibration decision already in the plan.

`test_strapdown_reproduces_a_clean_trajectory` is the load-bearing test here:
without it, "the naive baseline drifts badly" is not evidence of anything,
because a broken integrator also drifts badly. It integrates 20 s of coherent
synthetic data with exact initial attitude and requires under 5% divergence.

## Two filters, and why

`filter/ekf.py` is a 21-state strapdown error-state EKF with its transition and
measurement Jacobians verified against finite differences of the nonlinear
propagation (`tests/test_ekf.py`). That check is the point: a hand-derived
Jacobian that is never verified is the classic way a Kalman filter ends up
running fine while its covariance is quietly wrong.

It still cannot be used on IO-VNBD. The phone logs at 10 Hz, so the
accelerometer is aliased rather than merely coarse, and with GNSS fixes 9 s
apart there are ~90 free double-integration steps between corrections. Any
attitude error becomes `0.5·g·sin(tilt)·t²` of position error — at 9 s, a 2°
tilt is 14 m and a 20° tilt is 140 m. Run on this data it reached 5×10⁴ m/s.

`filter/kinematic.py` is the deployed path: five states (east, north, heading,
speed, gyro bias), heading integrated from the gyroscope, speed held. It never
double-integrates acceleration. Keep the strapdown for the Android app, where
the IMU runs at 100–200 Hz.

## Device-to-car alignment is a prerequisite

A phone sits at an arbitrary orientation in the vehicle, so the nonholonomic
constraint — no lateral or vertical velocity **in the car frame** — cannot be
applied until that rotation is known. Applying it in the phone's frame gave
1,312 m at a 10 s horizon, four times *worse* than an unaided strapdown.

`filter/alignment.py` recovers it from the correlation between horizontal
specific force and GNSS-derived longitudinal acceleration, and reports a
quality score; below threshold the constraint is disabled rather than applied
in the wrong frame. Observable in ~84% of runs.

One detail that decides whether it works at all: pair each interval's *mean*
horizontal specific force with that interval's mean acceleration. Pairing
against a single endpoint sample returned quality 0.0 on every sequence — the
estimator silently never worked. GNSS fixes are 9 s apart, so `dv/dt` is
already an interval average, and matching a smoothed quantity against an
unsmoothed one collapses the correlation into noise.

## Honest confidence

The filter is overconfident by more than an order of magnitude. On held-out
routes, nominal 90% ellipses contain **17%** of errors:

| Horizon | λ | NEES median | Coverage raw | Coverage calibrated |
|---|---|---|---|---|
| 10 s | 21.8 | 152.8 | 0.02 | 1.00 |
| 30 s | 15.5 | 130.4 | 0.11 | 0.91 |
| 60 s | 17.1 | 62.6 | 0.15 | 0.95 |
| 120 s | 17.0 | 25.7 | 0.22 | 1.00 |
| 180 s | 14.7 | 18.5 | 0.35 | 1.00 |
| **mean** | | | **0.17** | **0.97** |

`evaluation/conformal.py` fits one scalar inflation factor per horizon on the
val fold and measures containment on test, which the factors never saw. It
overshoots the nominal 90% because the fitting sets are 22–40 points and the
split-conformal quantile is conservative at that size — conservative is the
safe direction.

**Say "empirically calibrated coverage on held-out routes". Never
"guaranteed".** Trajectory errors are autocorrelated within an outage and grow
with elapsed time, so exchangeability fails and the conformal guarantee does
not hold. Fitting per horizon removes the largest part of that violation, which
is why the factors are stratified rather than pooled.

## The learned speed front end

`models/speednet.py` — DeepOdo/DeepOri convolutions and a GRU, plus GNIO's
Motion Bank and gated head. **128,083 parameters: 0.51 MB fp32, ~0.13 MB INT8**,
against a 5 MB budget.

Three design choices worth knowing:

- **Rotation-invariant features, not raw axes.** There are only ~14,000 speed
  labels in the whole dataset, one per real GNSS fix. That is far too few to
  learn 3-D rotation invariance from scratch, and a network that half-learns it
  generalises to a new mounting by luck. The six channels depend on the device
  frame only through the gravity direction.
- **Last-known GNSS speed is deliberately not an input.** Feeding it lets the
  network minimise its loss by echoing its input — excellent in training,
  useless during the blackout it exists to survive.
- **A [0,1] gate, not GNIO's Tanh.** GNIO's ablation validates Tanh for a
  *signed displacement vector*; forward speed is a non-negative scalar, where a
  [-1,1] gate can only reach zero by cancelling against the magnitude branch.
  Sigmoid keeps the property that matters: a smooth drive to zero, i.e. a
  differentiable ZUPT rather than a hard threshold. Both are selectable so the
  choice is measured.

Trained with the two-stage TLIO/GNIO schedule — MSE first, then Gaussian NLL.
Training NLL from scratch lets a model escape by predicting a huge variance
everywhere. The predicted sigma becomes the filter's measurement noise, so a
network that knows it is guessing widens the gate instead of dragging the
estimate.
