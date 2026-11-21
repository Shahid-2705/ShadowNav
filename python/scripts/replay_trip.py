"""Replay an Android trip CSV through the kinematic dead-reckoning pipeline.

Accepts both the 26-column TripRecorder v1 format and the 38-column raw-sample
format with IMU and raw GPS fixes.

Usage:
    PYTHONPATH=. python scripts/replay_trip.py path/to/shadownav-*.csv [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence as PySequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav import pipeline_kinematic as pipeline  # noqa: E402
from shadownav.data.iovnbd import Sequence  # noqa: E402
from shadownav.data.trip_csv import BlackoutSpan, Trip, read_trip  # noqa: E402
from shadownav.evaluation import masking, metrics  # noqa: E402
from shadownav.map import heading_constraint as hc  # noqa: E402
from shadownav.map import osm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "eval" / "results"
REACQ_TAIL_ROWS = 400


def load_conformal_factors(path: Path | None = None) -> dict[float, float]:
    """Load per-horizon inflation factors from shared/conformal.json."""
    if path is None:
        path = ROOT / "shared" / "conformal.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    return {float(h): float(v) for h, v in blob.get("factors", {}).items()}


def nearest_factor(factors: dict[float, float], horizon_s: float) -> float:
    """Return the inflation factor for the nearest horizon (larger in tie)."""
    if not factors:
        return 1.0
    nearest = min(factors.keys(), key=lambda h: (abs(h - horizon_s), -h))
    return float(factors[nearest])


def _self_consistency(trip: Trip, factors: dict[float, float]) -> list[dict]:
    """Evaluate self-consistency telemetry from a TripRecorder v1 CSV."""
    df = trip.sequence.df
    t = trip.sequence.time_s
    out = []
    modes = df["app_mode"].to_numpy(dtype=object) if "app_mode" in df.columns else np.full(len(df), "")

    for span in trip.info.spans:
        df_span = df.iloc[span.start_row : span.end_row]
        dr_dist = (
            float(df_span["app_dr_distance_m"].iloc[-1])
            if "app_dr_distance_m" in df_span.columns
            else 0.0
        )

        dr_rows = np.flatnonzero(modes[span.start_row : span.end_row] == "DEAD_RECKONING")
        if dr_rows.size:
            det_latency = float(t[span.start_row + dr_rows[0]] - span.start_s)
        else:
            det_latency = float("nan")

        sig = (
            float(df_span["app_sigma_m"].iloc[-1])
            if "app_sigma_m" in df_span.columns
            else float("nan")
        )
        lam = nearest_factor(factors, span.duration_s)
        cal_r = lam * 2.146 * sig if np.isfinite(sig) else float("nan")

        # Measure duration spent in REACQUIRING immediately after blackout
        k = span.end_row
        while k < len(modes) and modes[k] == "REACQUIRING":
            k += 1
        if k > span.end_row:
            settle_s = float(t[k] - t[span.end_row])
        else:
            settle_s = float("nan")

        out.append({
            "span": span.as_dict(),
            "app_dr_distance_m": dr_dist,
            "app_detection_latency_s": det_latency,
            "app_radius90_cal_m": cal_r,
            "app_reacq_settle_s": settle_s,
        })
    return out


def replay(
    path: str | Path,
    *,
    horizons: PySequence[float] = (10.0, 30.0, 60.0),
    out: Path | None = None,
    factors: dict[float, float] | None = None,
    config: pipeline.KinematicPipelineConfig | None = None,
    osm_network: str | Path | osm.RoadNetwork | None = None,
) -> dict:
    """Replay one recorded drive CSV, scoring recorded and synthetic outages."""
    path = Path(path)
    trip = read_trip(path)
    factors = factors if factors is not None else load_conformal_factors()
    cfg = config or pipeline.KinematicPipelineConfig()

    road_net: osm.RoadNetwork | None = None
    if osm_network is not None:
        if isinstance(osm_network, osm.RoadNetwork):
            road_net = osm_network
        else:
            p_osm = Path(osm_network)
            if p_osm.exists():
                blob = json.loads(p_osm.read_text(encoding="utf-8"))
                road_net = osm.parse_overpass(blob, name=p_osm.stem)

    if not trip.info.replayable:
        sc = _self_consistency(trip, factors)
        report = {
            "method": "device_replay",
            "seed": 20260905,
            "n_sequences": 1,
            "n_outages": 0,
            "summary": {},
            "results": [],
            "device": {
                "name": trip.info.name,
                "path": str(trip.info.path),
                "replayable": False,
                "ground_truth": "none (TripRecorder v1 format carries no raw IMU or raw GNSS)",
                "imu_rate_hz_measured": trip.info.imu_rate_hz,
                "imu_max_gap_ms": trip.info.max_gap_ms,
                "mask_source": trip.info.mask_source,
                "sats_source": trip.info.sats_source,
                "n_recorded_blackouts": len(trip.info.spans),
                "recorded_blackouts": [s.as_dict() for s in trip.info.spans],
                "self_consistency": sc,
            },
        }
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # Make an isolated copy so the original dataframe is never mutated
    seq = Sequence(
        name=trip.sequence.name,
        path=trip.sequence.path,
        df=trip.sequence.df.copy(),
        repair=trip.sequence.repair,
    )

    t = seq.time_s
    ref_lat, ref_lon = pipeline.enu_reference(seq)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(),
        seq.df["gps_lon_deg"].to_numpy(),
        ref_lat,
        ref_lon,
    )
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())

    results: list[dict] = []
    outage_results: list[metrics.OutageResult] = []

    # 1. Run pipeline over the full trip to score recorded blackouts
    try:
        full_traj = pipeline.run(seq, config=cfg)
    except (ValueError, np.linalg.LinAlgError):
        full_traj = None

    if full_traj is not None:
        est_e = full_traj.east_m
        est_n = full_traj.north_m
        speed = full_traj.speed_ms
        mode = full_traj.mode
        cov = full_traj.cov_xy

        for span in trip.info.spans:
            usable = fix_rows[fix_rows >= span.end_row]
            if not usable.size:
                continue
            eval_row = int(usable[0])
            t_eval_s = float(t[eval_row] - t[span.start_row])
            dist_m = float(np.sum(np.hypot(
                np.diff(true_e[span.start_row : eval_row + 1]),
                np.diff(true_n[span.start_row : eval_row + 1]),
            )))

            res = metrics.evaluate_window(
                sequence=seq.name,
                method="device_replay",
                horizon_s=span.duration_s,
                time_s=t,
                est_e=est_e,
                est_n=est_n,
                true_e=true_e,
                true_n=true_n,
                fix_rows=usable,
                start_row=span.start_row,
                distance_m=dist_m,
                n_fixes_suppressed=span.n_fixes_inside,
                cov_xy=cov,
            )
            if res is None:
                continue

            transitions = metrics.transition_metrics(
                time_s=t,
                mode=mode,
                est_e=est_e,
                est_n=est_n,
                speed_ms=speed,
                true_e=true_e,
                true_n=true_n,
                fix_rows=fix_rows,
                start_row=span.start_row,
                mask_end_row=span.end_row,
            )
            lam = nearest_factor(factors, span.duration_s)
            raw_r = metrics.calibrated_radius(cov[eval_row], 1.0)
            cal_r = metrics.calibrated_radius(cov[eval_row], lam)

            full_res = metrics.OutageResult(
                **{
                    **res.as_dict(),
                    **transitions.as_dict(),
                    "radius90_raw_m": raw_r,
                    "radius90_cal_m": cal_r,
                }
            )
            outage_results.append(full_res)
            res_dict = full_res.as_dict()
            res_dict["kind"] = "recorded"
            res_dict["start_s"] = float(span.start_s)
            res_dict["meets_10pct_target"] = bool(res.drift_pct < 10.0)
            results.append(res_dict)

    # 2. Plan and evaluate synthetic outages on continuous spans
    for horizon in horizons:
        candidates = masking.plan_outages(
            seq,
            horizon,
            n=5,
            seed=20260905,
            min_speed_ms=1.0,
            guard_s=5.0,
        )
        for w in candidates:
            # Check overlap with any recorded blackout
            overlap = any(
                (w.start_s < s.end_s and w.start_s + w.duration_s > s.start_s)
                for s in trip.info.spans
            )
            if overlap:
                continue

            eval_row = metrics.evaluation_row(t, fix_rows, w.start_row, horizon)
            if eval_row is None:
                continue

            scored = masking.extend_to_row(seq, w, eval_row)
            masked = masking.apply_mask(seq, scored)
            rate_hz = trip.info.imu_rate_hz if trip.info.imu_rate_hz > 0 else 10.0
            tail_samples = int(max(REACQ_TAIL_ROWS, 40.0 * rate_hz))
            run_end = min(len(seq) - 1, eval_row + tail_samples)
            warm = max(0, w.start_row - int(30.0 * rate_hz))

            try:
                traj = pipeline.run(masked, config=cfg, start_row=warm, end_row=run_end)
            except (ValueError, np.linalg.LinAlgError):
                continue

            synth_e = np.full(len(seq), np.nan)
            synth_n = np.full(len(seq), np.nan)
            synth_v = np.full(len(seq), np.nan)
            synth_mode = np.full(len(seq), None, dtype=object)
            synth_cov = np.zeros((len(seq), 2, 2))
            sl = slice(warm, run_end + 1)
            synth_e[sl] = traj.east_m
            synth_n[sl] = traj.north_m
            synth_v[sl] = traj.speed_ms
            synth_mode[sl] = traj.mode
            synth_cov[sl] = traj.cov_xy

            res = metrics.evaluate_window(
                sequence=seq.name,
                method="device_replay",
                horizon_s=horizon,
                time_s=t,
                est_e=synth_e,
                est_n=synth_n,
                true_e=true_e,
                true_n=true_n,
                fix_rows=fix_rows,
                start_row=w.start_row,
                distance_m=scored.distance_m,
                n_fixes_suppressed=scored.n_fixes_suppressed,
                cov_xy=synth_cov,
            )
            if res is None:
                continue

            transitions = metrics.transition_metrics(
                time_s=t,
                mode=synth_mode,
                est_e=synth_e,
                est_n=synth_n,
                speed_ms=synth_v,
                true_e=true_e,
                true_n=true_n,
                fix_rows=fix_rows,
                start_row=w.start_row,
                mask_end_row=scored.end_row,
            )
            lam = nearest_factor(factors, horizon)
            raw_r = metrics.calibrated_radius(synth_cov[eval_row], 1.0)
            cal_r = metrics.calibrated_radius(synth_cov[eval_row], lam)

            synth_res = metrics.OutageResult(
                **{
                    **res.as_dict(),
                    **transitions.as_dict(),
                    "radius90_raw_m": raw_r,
                    "radius90_cal_m": cal_r,
                }
            )
            outage_results.append(synth_res)
            res_dict = synth_res.as_dict()
            res_dict["kind"] = "synthetic"
            res_dict["start_s"] = float(w.start_s)
            res_dict["meets_10pct_target"] = bool(res.drift_pct < 10.0)

            if road_net is not None:
                try:
                    observer = hc.HeadingObserver.from_network(road_net, ref_lat, ref_lon)
                    traj_mm = pipeline.run(
                        masked, config=cfg, start_row=warm, end_row=run_end, heading_observer=observer,
                    )
                    synth_e_mm = np.full(len(seq), np.nan)
                    synth_n_mm = np.full(len(seq), np.nan)
                    synth_e_mm[sl] = traj_mm.east_m
                    synth_n_mm[sl] = traj_mm.north_m
                    res_mm = metrics.evaluate_window(
                        sequence=seq.name,
                        method="device_replay",
                        horizon_s=horizon,
                        time_s=t,
                        est_e=synth_e_mm,
                        est_n=synth_n_mm,
                        true_e=true_e,
                        true_n=true_n,
                        fix_rows=fix_rows,
                        start_row=w.start_row,
                        distance_m=scored.distance_m,
                        n_fixes_suppressed=scored.n_fixes_suppressed,
                    )
                    if res_mm is not None:
                        res_dict["map_matched_drift_m"] = float(res_mm.drift_m)
                        res_dict["map_matched_drift_pct"] = float(res_mm.drift_pct)
                        res_dict["gain_from_map_matching_pct"] = float(
                            (res.drift_m - res_mm.drift_m) / max(res.drift_m, 1e-3) * 100.0
                        )
                        res_dict["map_decisions"] = observer.counts()
                except Exception:
                    pass

            results.append(res_dict)

    summary_raw = metrics.summarise(outage_results)
    summary = {f"{h:.1f}": v for h, v in summary_raw.items()}

    report = {
        "method": "device_replay",
        "seed": 20260905,
        "n_sequences": 1,
        "n_outages": len(results),
        "summary": summary,
        "results": results,
        "device": {
            "name": trip.info.name,
            "path": str(trip.info.path),
            "replayable": True,
            "ground_truth": "recorded fixes (simulated blackout during continuous driving)",
            "imu_rate_hz_measured": trip.info.imu_rate_hz,
            "imu_max_gap_ms": trip.info.max_gap_ms,
            "mask_source": trip.info.mask_source,
            "sats_source": trip.info.sats_source,
            "n_recorded_blackouts": len(trip.info.spans),
            "recorded_blackouts": [s.as_dict() for s in trip.info.spans],
        },
    }

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path, help="path to trip CSV")
    ap.add_argument(
        "--horizons",
        nargs="+",
        type=float,
        default=[10.0, 30.0, 60.0],
        help="synthetic horizons (default: 10 30 60)",
    )
    ap.add_argument("--osm-network", type=Path, default=None, help="path to Overpass OSM JSON")
    ap.add_argument("--out", type=Path, default=None, help="output JSON path")
    args = ap.parse_args(argv)

    out = args.out
    if out is None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / f"device_replay_{args.path.stem}.json"

    report = replay(args.path, horizons=tuple(args.horizons), out=out, osm_network=args.osm_network)
    print(f"Replay complete: {report['n_outages']} outages scored -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
