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
  data/      IO-VNBD loading, schema resolution, defect repair, fetching
  evaluation/ synthetic outage masking, metrics, the published split
  baselines/ naive strapdown INS — the drift floor
  utils/     determinism
  geo.py     WGS84 -> local ENU
scripts/
  audit_gps_rate.py   measures the real GPS fix rate (see below)
  run_baseline.py     produces eval/results/baseline_naive.json
```

## Reproducing the numbers

```bash
PYTHONPATH=. python scripts/audit_gps_rate.py    # -> eval/results/gps_rate_audit.json
PYTHONPATH=. python scripts/run_baseline.py      # -> eval/results/baseline_naive.json
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

There are only **14,212 real position observations in the whole dataset**. This
is not a detail — it sets what the data can and cannot answer:

* a 10 s outage suppresses roughly one real fix, a 30 s outage roughly three;
* scoring at 10 Hz against interpolated truth would report interpolation error
  as estimator error, and between fixes 27 m apart on a curve that is metres.

So metrics are evaluated **only at rows carrying a real fix**, each result
reports the actual elapsed time (which can exceed the requested horizon by up to
one fix period), and `truth_gap_m` is reported alongside every number.

A latitude-only change test reports the fix rate wrongly by an order of
magnitude, because on a near-east/west drive latitude is constant to 6 decimal
places for scores of rows while longitude advances every fix. Fix detection uses
the whole GPS tuple.

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
