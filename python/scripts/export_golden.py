"""Export golden vectors so the Kotlin filter can be proved equal to the Python one.

shared/README.md makes this a requirement, not a nicety: "Verify the Kotlin path
reproduces the Python path numerically on a fixed replay before trusting any
on-device number."

Without it, a sign error or a transposed matrix in the port produces a
trajectory that looks entirely plausible on a phone screen and is wrong. The
Android app has no ground truth to notice with.

Each case records inputs and the exact expected state after a fixed sequence of
operations. The Kotlin tests replay them and assert agreement to 1e-9.

Run:  PYTHONPATH=. python scripts/export_golden.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav.filter.alignment import estimate_alignment  # noqa: E402
from shadownav.filter.fsm import BlendState  # noqa: E402
from shadownav.filter.kinematic import KinematicEKF  # noqa: E402
from shadownav.models.features import gravity_direction, invariant_features  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "android" / "shadownav-core" / \
    "src" / "test" / "resources" / "golden"


def rnd(x, n=12):
    if isinstance(x, np.ndarray):
        return [rnd(v, n) for v in x.tolist()]
    if isinstance(x, (list, tuple)):
        return [rnd(v, n) for v in x]
    return round(float(x), n)


def case_geo() -> dict:
    lat = np.array([52.881744, 52.882000, 52.883500, 53.250540])
    lon = np.array([-1.717480, -1.717000, -1.715000, -1.910692])
    e, n = geo.lla_to_enu(lat, lon)
    return {
        "description": "WGS84 lat/lon -> local ENU, and curvature radii",
        "lat_deg": rnd(lat), "lon_deg": rnd(lon),
        "east_m": rnd(e), "north_m": rnd(n),
        "curvature_radii_53deg": rnd(np.array(geo.curvature_radii(53.0))),
        "path_length_m": rnd(geo.path_length(e, n)),
        "heading_from_track_rad": rnd(geo.heading_from_track(e, n)),
    }


def case_propagate() -> dict:
    """Straight, then a sustained right turn, then a left turn."""
    f = KinematicEKF(10.0, -5.0, 0.3, 12.0)
    gyro = ([0.0] * 20) + ([-0.15] * 40) + ([0.08] * 30)
    for g in gyro:
        f.propagate(g, None, 0.1)
    return {
        "description": "90 propagation steps at dt=0.1, no measurements",
        "init": {"east": 10.0, "north": -5.0, "heading": 0.3, "speed": 12.0},
        "gyro_z": rnd(np.array(gyro)),
        "dt": 0.1,
        "state": rnd(f.x),
        "cov_diag": rnd(np.diag(f.cov)),
    }


def case_propagate_with_accel() -> dict:
    f = KinematicEKF(0.0, 0.0, 0.0, 5.0)
    gyro = [0.02] * 50
    accel = [0.4] * 25 + [-0.6] * 25
    for g, a in zip(gyro, accel):
        f.propagate(g, a, 0.1)
    return {
        "description": "propagation with forward acceleration supplied",
        "init": {"east": 0.0, "north": 0.0, "heading": 0.0, "speed": 5.0},
        "gyro_z": rnd(np.array(gyro)), "accel_forward": rnd(np.array(accel)),
        "dt": 0.1, "state": rnd(f.x), "cov_diag": rnd(np.diag(f.cov)),
    }


def case_updates() -> dict:
    """Every measurement type, in a fixed order."""
    f = KinematicEKF(0.0, 0.0, 0.1, 8.0)
    log = []
    for i in range(30):
        f.propagate(0.05, None, 0.1)
        if i % 10 == 0:
            accepted = f.update_position(np.array([float(i), -float(i) * 0.5]))
            f.update_speed(9.0)
            f.update_course(0.2)
            log.append({"step": i, "position_accepted": bool(accepted)})
    f.update_centripetal(-8.0 * 0.05, 0.05)
    applied_ack = f.update_ackermann(0.5)
    return {
        "description": "position, speed, course, centripetal and Ackermann updates",
        "init": {"east": 0.0, "north": 0.0, "heading": 0.1, "speed": 8.0},
        "log": log,
        "ackermann_applied": bool(applied_ack),
        "state": rnd(f.x), "cov_diag": rnd(np.diag(f.cov)),
        "n_gps_accepted": f.diagnostics.n_gps_accepted,
        "n_gps_rejected": f.diagnostics.n_gps_rejected,
        "n_centripetal": f.diagnostics.n_centripetal,
        "n_ackermann": f.diagnostics.n_ackermann,
    }


def case_gate_escape() -> dict:
    """Three wild fixes must trigger a re-anchor, not permanent lockout."""
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    accepted = [bool(f.update_position(np.array([5000.0, 5000.0]))) for _ in range(3)]
    return {
        "description": "consecutive rejection triggers reanchor",
        "accepted": accepted,
        "state": rnd(f.x),
        "n_gate_overrides": f.diagnostics.n_gate_overrides,
    }


def case_ackermann() -> dict:
    rows = []
    for speed, gyro in [(0.2, 0.5), (20.0, 0.5), (40.0, 0.5),
                        (10.0, 0.2), (10.0, 0.001), (2.0, 3.0)]:
        f = KinematicEKF(0.0, 0.0, 0.0, speed)
        applied = f.update_ackermann(gyro)
        rows.append({"speed_in": speed, "gyro_z": gyro,
                     "applied": bool(applied), "speed_out": rnd(f.speed_ms)})
    return {"description": "Ackermann curvature and friction bounds", "cases": rows}


def case_blend() -> dict:
    b = BlendState(2.3)
    b.start(np.array([20.0, -15.0]))
    trace = [rnd(b.step(0.02)) for _ in range(200)]
    return {
        "description": "critically damped reacquisition blend, omega=2.3, dt=0.02",
        "initial_error": [20.0, -15.0], "omega": 2.3, "dt": 0.02,
        "samples": [trace[i] for i in (0, 9, 49, 99, 199)],
        "sample_indices": [0, 9, 49, 99, 199],
        "settled": bool(b.settled),
    }


def case_alignment() -> dict:
    rng = np.random.default_rng(11)
    n = 1200
    t = np.arange(n) * 0.1
    v = 10.0 + 4.0 * np.sin(2 * np.pi * t / 60.0)
    a = np.gradient(v, 0.1)
    acc = np.stack([np.zeros(n), a, np.full(n, 9.80665)], axis=1)
    acc += rng.normal(0, 0.05, acc.shape)
    gyr = rng.normal(0, 0.002, (n, 3))
    held = v.copy()
    for i in range(0, n, 90):
        held[i : i + 90] = v[i]
    out = estimate_alignment(acc, gyr, held, t)
    return {
        "description": "device-to-car alignment from specific force vs GNSS accel",
        "acc": rnd(acc, 9), "gyr": rnd(gyr, 9),
        "speed_ms": rnd(held, 9), "time_s": rnd(t, 9),
        "quality": rnd(out.quality), "n_samples": out.n_samples,
        "rot_device_to_car": rnd(out.rot_device_to_car),
    }


def case_features() -> dict:
    rng = np.random.default_rng(5)
    acc = rng.normal(0, 1.0, (64, 3)) + np.array([0.0, 0.0, 9.81])
    gyr = rng.normal(0, 0.1, (64, 3))
    up = gravity_direction(acc)
    feat = invariant_features(acc, gyr, up)
    return {
        "description": "rotation-invariant feature channels",
        "acc": rnd(acc, 9), "gyr": rnd(gyr, 9),
        "up": rnd(up), "features": rnd(feat),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = {
        "geo": case_geo(),
        "propagate": case_propagate(),
        "propagate_accel": case_propagate_with_accel(),
        "updates": case_updates(),
        "gate_escape": case_gate_escape(),
        "ackermann": case_ackermann(),
        "blend": case_blend(),
        "alignment": case_alignment(),
        "features": case_features(),
    }
    for name, blob in cases.items():
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(blob, indent=1), encoding="utf-8")
        print(f"  {path.name:22s} {path.stat().st_size / 1024:7.1f} KB  "
              f"{blob['description']}")
    print(f"\nwrote {len(cases)} golden cases to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
