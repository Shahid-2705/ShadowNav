"""Fetch and cache the OSM road network around every test-fold (and val) route.

One Overpass request per sequence: the GNSS track's bounding box, padded, all
``highway=*`` ways, cached as raw JSON under ``data/osm/``. Re-runs are cache
hits and cost nothing. A sequence whose map cannot be fetched is reported and
left without a map -- the ablation then runs with the constraint disabled on
it, and says so.

Run:  PYTHONPATH=. python scripts/fetch_osm.py [--fold test|val|both] [--max-km 40]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import splits  # noqa: E402
from shadownav.map import osm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OSM_DIR = ROOT / "data" / "osm"


def cache_name(sequence_name: str) -> str:
    """``S-M#1`` -> ``S-M_1``: session suffixes are not filename-friendly."""
    return sequence_name.replace("#", "_")


def sequence_bbox(seq: iovnbd.Sequence, pad_m: float) -> osm.BBox:
    return osm.BBox.from_track(
        seq.df["gps_lat_deg"].to_numpy(dtype=float),
        seq.df["gps_lon_deg"].to_numpy(dtype=float),
        pad_m=pad_m,
    )


def iter_fold_sequences(folds: tuple[str, ...]):
    split = splits.load_split()
    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    for path in sorted(data_dir.glob("S-*.csv")):
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError:
            continue
        for seq in sessions:
            fold = split.fold_of(seq.name)
            if fold in folds:
                yield fold, seq


def fetch_for(seq: iovnbd.Sequence, pad_m: float, timeout_s: float) -> tuple[osm.BBox, osm.FetchResult]:
    box = sequence_bbox(seq, pad_m)
    return box, osm.fetch_highways(cache_name(seq.name), box, OSM_DIR, timeout_s=timeout_s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", default="test", choices=["test", "val", "both"])
    ap.add_argument("--pad-m", type=float, default=300.0)
    ap.add_argument("--max-km", type=float, default=40.0,
                    help="skip routes whose padded bbox exceeds this on either side")
    ap.add_argument("--timeout-s", type=float, default=300.0)
    args = ap.parse_args(argv)

    folds = ("test", "val") if args.fold == "both" else (args.fold,)
    print(f"{'sequence':<12} {'fold':<5} {'bbox km':>13} {'ways':>6} {'junc':>6} "
          f"{'source':<9} {'MB':>6} {'s':>6}  note")
    n_err = 0
    for fold, seq in iter_fold_sequences(folds):
        box = sequence_bbox(seq, args.pad_m)
        ns, ew = box.size_km
        if max(ns, ew) > args.max_km:
            print(f"{seq.name:<12} {fold:<5} {ns:5.1f} x {ew:5.1f} {'-':>6} {'-':>6} "
                  f"{'skipped':<9} {'-':>6} {'-':>6}  bbox above --max-km")
            continue
        _, res = fetch_for(seq, args.pad_m, args.timeout_s)
        net = res.network
        ways = net.n_ways if net else 0
        junc = len(net.junction_nodes) if net else 0
        note = "" if res.source != "error" else res.message[:120]
        n_err += res.source == "error"
        print(f"{seq.name:<12} {fold:<5} {ns:5.1f} x {ew:5.1f} {ways:>6} {junc:>6} "
              f"{res.source:<9} {res.n_bytes / 1e6:>6.1f} {res.elapsed_s:>6.1f}  {note}")
        sys.stdout.flush()
    if n_err:
        print(f"\n{n_err} route(s) have no map. The ablation will run those with the "
              f"constraint disabled and report it.")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
