# `shared/` — the Python ↔ Android contract

Everything here is produced by the Python pipeline and consumed by the Android
runtime. **Nothing in this directory may be edited by hand.** Regenerate it:

```bash
cd python
PYTHONPATH=. python scripts/train_speednet.py --epochs 70   # -> speednet.pt
PYTHONPATH=. python scripts/calibrate_confidence.py         # -> conformal.json
```

## `speednet.pt` — forward-speed network

| | |
|---|---|
| Architecture | CNN + GRU + Motion Bank + gated head (`shadownav/models/speednet.py`) |
| Parameters | 128,083 |
| Size | 0.52 MB float32 · ~0.13 MB INT8 |
| Latency | 2.36 ms median, 3.71 ms p95, single thread, float32 |
| Budget | 5 MB INT8, 30 ms per 10 Hz update |

Loadable with `weights_only=True`. Keep it that way: `torch.load` defaults to
unpickling arbitrary Python objects, which is arbitrary code execution on any
checkpoint not produced locally. Standardisation statistics are stored as
tensors, not numpy arrays, precisely so safe loading works.

### Keys

| Key | Type | Meaning |
|---|---|---|
| `state_dict` | tensors | model weights |
| `config` | dict | `SpeedNetConfig` fields; reconstruct the module from these, never assume defaults |
| `feature_mean` | float64[6] | per-channel mean, fitted on **train only** |
| `feature_std` | float64[6] | per-channel std, fitted on **train only** |
| `window` | int | 64 samples |
| `sigma_scale` | float | multiplies the head's reported σ (see below) |
| `variant` | str | which ablation variant won |
| `seed` | int | 20260905 |

### Input contract

Six **rotation-invariant** channels over a causal window of `window` samples,
standardised by `(x - feature_mean) / feature_std`:

```
0  |a|            specific-force magnitude
1  a · up         vertical specific force
2  |a_horiz|      horizontal specific-force magnitude
3  |w|            angular-rate magnitude
4  w · up         yaw rate
5  |w_horiz|      pitch/roll rate magnitude
```

`up` is the unit vertical **in device coordinates**, from the long-run mean
specific force. Fix it once per drive from aided data — re-estimating it per
window reintroduces a tilt error worth hundreds of metres (see
`baselines/naive.py`).

The window must **end** at the prediction instant. It must never contain future
samples: a non-causal window scores well offline and cannot be deployed.

Raw axes are deliberately not the input. There are only ~14,000 speed labels in
the whole dataset, far too few to learn 3-D rotation invariance from data, and a
network that half-learns it generalises to a new mounting by luck.

Last-known GNSS speed is deliberately **not** an input. Feeding it lets the
network minimise its loss by echoing its input — excellent in training, useless
during the blackout it exists to survive.

### Output contract

`(speed_ms, log_var)`. The reported standard deviation is

```
sigma = exp(0.5 * log_var) * sigma_scale
```

**`sigma_scale` is not optional.** The NLL head is systematically
under-dispersed: raw 1σ coverage is 0.27 against the 0.6827 a calibrated
Gaussian gives. That σ becomes the filter's measurement noise `R`, so an
uncalibrated head makes the filter over-trust a biased estimate — measured as
NEES rising from 29–84 to 746–2650 and 180 s error getting *worse* when the
network was first wired in. The scale is fitted on the val fold (currently
3.27×, taking coverage to 0.64).

Clamp the result to `[0.4, 8.0]` m/s, as `models/inference.py` does, so a
diverging head cannot emit a σ the filter either blindly trusts or entirely
ignores.

## `conformal.json` — position-covariance inflation

Per-horizon scalar λ. Report `P_reported = λ² · P_filter`.

The filter is overconfident by more than an order of magnitude: nominal 90%
ellipses contain **17%** of errors on held-out routes. Fitted on val, measured
on test.

**Claim wording is part of the contract.** Say *"empirically calibrated
coverage — 90% containment on held-out routes"*. Never *"guaranteed"*.
Trajectory errors are autocorrelated within an outage and grow with elapsed
time, so exchangeability fails and the conformal guarantee does not hold.
Stratifying per horizon removes the largest part of that violation, which is
why λ is fitted per horizon rather than pooled.

## For the Android port

1. Reconstruct the module from `config`, never from defaults.
2. Apply `feature_mean` / `feature_std` exactly — a mismatch here is silent.
3. Apply `sigma_scale`. It is the difference between honest and dangerous.
4. Verify the Kotlin path reproduces the Python path numerically on a fixed
   replay before trusting any on-device number.
5. Re-run the ablations at 100–200 Hz. Every negative result in this project —
   the 21-state strapdown, `L_cent`, accelerometer-driven speed, and the
   ceiling on this network — traces to IO-VNBD's 10 Hz logging aliasing the
   vibration signature away. None of them are refuted; they are untested at the
   rate a phone actually provides.
