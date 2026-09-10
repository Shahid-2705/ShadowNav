"""OpenStreetMap road geometry: fetch, cache, parse, project.

Deliberately dependency-free -- ``urllib`` rather than ``requests``, no
``osmnx``/``geopandas``. The offline story in the problem statement means the
road network has to be something the project can ship, so it is fetched once
per route into a JSON cache and read from there afterwards.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import geo

#: Ways a car cannot drive on. Service roads are deliberately **kept**: they
#: are the parallel-carriageway ambiguity Track C uses to argue that a heading
#: constraint is safe where a lateral one is not, so dropping them would hide
#: the case the design exists to handle.
EXCLUDED_HIGHWAYS = frozenset({
    "footway", "path", "steps", "cycleway", "pedestrian", "bridleway",
    "corridor", "platform", "proposed", "construction", "raceway",
})

#: Tried in order. Measured 2026-09-10 from this machine: the kumi mirror
#: answered ``/api/status`` in 0.8 s and the main server in 5.4 s, and the
#: main server dropped one POST without a reply, so the mirror goes first.
DEFAULT_ENDPOINTS: tuple[str, ...] = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
)

#: OSM documents these as one-way without the tag.
IMPLIED_ONEWAY_HIGHWAYS = frozenset({"motorway", "motorway_link"})

USER_AGENT = "ShadowNav/0.1 (SIH26168 research; contact via repository)"

#: Metres per degree of latitude, WGS84 mean. Only used for padding a bounding
#: box, where a tenth of a percent is irrelevant.
M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class BBox:
    """Geographic bounding box, in the order Overpass wants it."""

    south: float
    west: float
    north: float
    east: float

    @classmethod
    def from_track(cls, lat: np.ndarray, lon: np.ndarray, pad_m: float = 300.0) -> "BBox":
        """Box around a GNSS track, padded by ``pad_m`` on every side.

        The padding matters: a vehicle sits beside the road centreline, and a
        box drawn tightly around the fixes clips the very ways the constraint
        needs at the start and end of a drive.
        """
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        lat = lat[np.isfinite(lat)]
        lon = lon[np.isfinite(lon)]
        if lat.size == 0 or lon.size == 0:
            raise ValueError("no finite positions to build a bounding box from")

        box = cls(float(lat.min()), float(lon.min()), float(lat.max()), float(lon.max()))
        return box.padded(pad_m)

    def padded(self, pad_m: float) -> "BBox":
        d_lat = pad_m / M_PER_DEG_LAT
        mid = 0.5 * (self.south + self.north)
        d_lon = pad_m / (M_PER_DEG_LAT * max(math.cos(math.radians(mid)), 1e-6))
        return BBox(self.south - d_lat, self.west - d_lon, self.north + d_lat, self.east + d_lon)

    @property
    def size_km(self) -> tuple[float, float]:
        """(north-south, east-west) extent in km."""
        mid = 0.5 * (self.south + self.north)
        ns = (self.north - self.south) * M_PER_DEG_LAT / 1000.0
        ew = (self.east - self.west) * M_PER_DEG_LAT * math.cos(math.radians(mid)) / 1000.0
        return ns, ew

    def overpass(self) -> str:
        return f"{self.south:.6f},{self.west:.6f},{self.north:.6f},{self.east:.6f}"


# ``eq=False``: these carry numpy arrays, and a generated ``__eq__`` would
# raise on an ambiguous truth value the first time two of them are compared.
@dataclass(frozen=True, eq=False)
class Way:
    """One OSM way in geographic coordinates."""

    way_id: int
    highway: str
    oneway: int          # 0 both ways, +1 along the node order, -1 against it
    lat: np.ndarray
    lon: np.ndarray
    node_ids: tuple[int, ...]


@dataclass(frozen=True, eq=False)
class ProjectedWay:
    """One OSM way in the sequence's local ENU frame."""

    way_id: int
    highway: str
    oneway: int
    east: np.ndarray
    north: np.ndarray
    node_ids: tuple[int, ...]


@dataclass(frozen=True, eq=False)
class RoadNetwork:
    """Driveable ways plus the nodes where three or more arms meet."""

    name: str
    ways: tuple[Way, ...]
    junction_nodes: frozenset[int]

    @property
    def n_ways(self) -> int:
        return len(self.ways)


@dataclass(frozen=True, eq=False)
class FetchResult:
    """Outcome of a fetch. ``network`` is None unless ``source`` succeeded."""

    network: RoadNetwork | None
    source: str          # "cache" | "network" | "error"
    message: str = ""
    path: Path | None = None
    n_bytes: int = 0
    elapsed_s: float = 0.0


def _oneway(tags: dict) -> int:
    value = str(tags.get("oneway", "")).strip().lower()
    if value in {"yes", "true", "1"}:
        return 1
    if value in {"-1", "reverse"}:
        return -1
    if value in {"no", "false", "0"}:
        return 0
    if tags.get("junction") in {"roundabout", "circular"}:
        return 1
    return 1 if tags.get("highway") in IMPLIED_ONEWAY_HIGHWAYS else 0


def junction_nodes(ways: tuple[Way, ...]) -> frozenset[int]:
    """Nodes where at least three road arms meet.

    Degree is counted in *arms*, not way memberships: a node in the middle of a
    way has two arms there, a node at either end has one. A T-junction is then
    a node with three, which is what a lookahead has to avoid -- the vehicle
    may leave the current way there and the bearing stops being evidence.
    """
    arms: dict[int, int] = {}
    for way in ways:
        last = len(way.node_ids) - 1
        for i, node in enumerate(way.node_ids):
            arms[node] = arms.get(node, 0) + (1 if i in (0, last) else 2)
    return frozenset(node for node, count in arms.items() if count >= 3)


def parse_overpass(blob: dict, *, name: str) -> RoadNetwork:
    """Build a road network from an Overpass ``out geom`` response."""
    ways: list[Way] = []
    for element in blob.get("elements", ()):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        highway = tags.get("highway")
        if not highway or highway in EXCLUDED_HIGHWAYS:
            continue
        geometry = element.get("geometry") or []
        nodes = element.get("nodes") or []
        if len(geometry) < 2 or len(nodes) != len(geometry):
            continue
        ways.append(Way(
            way_id=int(element["id"]),
            highway=str(highway),
            oneway=_oneway(tags),
            lat=np.array([float(p["lat"]) for p in geometry]),
            lon=np.array([float(p["lon"]) for p in geometry]),
            node_ids=tuple(int(n) for n in nodes),
        ))
    return RoadNetwork(name=name, ways=tuple(ways),
                       junction_nodes=junction_nodes(tuple(ways)))


def project_network(
    network: RoadNetwork, ref_lat: float, ref_lon: float
) -> tuple[ProjectedWay, ...]:
    """Project every way into the ENU frame the estimator is running in.

    The reference must be the one ``pipeline_kinematic.enu_reference`` returns
    for the same sequence, or the roads land somewhere else entirely.
    """
    out: list[ProjectedWay] = []
    for way in network.ways:
        east, north = geo.lla_to_enu(way.lat, way.lon, ref_lat, ref_lon)
        out.append(ProjectedWay(
            way_id=way.way_id, highway=way.highway, oneway=way.oneway,
            east=east, north=north, node_ids=way.node_ids,
        ))
    return tuple(out)


def overpass_query(box: BBox, timeout_s: float = 120.0) -> str:
    return f'[out:json][timeout:{int(timeout_s)}];way["highway"]({box.overpass()});out geom;'


def _fetch_one(name: str, endpoint: str, box: BBox, path: Path, timeout_s: float) -> FetchResult:
    """One POST to one endpoint. Raises on any failure; the caller collects."""
    t0 = time.monotonic()
    payload = urllib.parse.urlencode({"data": overpass_query(box, timeout_s)}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    blob = json.loads(raw)
    remark = str(blob.get("remark", ""))
    if "error" in remark.lower():
        # Overpass reports a server-side time-out as a remark with 200 OK
        # and a truncated element list; that is a failure, not a map.
        raise ValueError(f"overpass remark: {remark}")
    elapsed = time.monotonic() - t0
    path.write_text(raw, encoding="utf-8")
    path.with_suffix(".meta.json").write_text(json.dumps({
        "name": name, "bbox": box.overpass(), "endpoint": endpoint, "bytes": len(raw),
        "elapsed_s": round(elapsed, 1),
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2), encoding="utf-8")
    return FetchResult(parse_overpass(blob, name=name), "network", "", path, len(raw), elapsed)


def fetch_highways(
    name: str,
    box: BBox,
    cache_dir: Path | str,
    *,
    endpoints: tuple[str, ...] = DEFAULT_ENDPOINTS,
    timeout_s: float = 120.0,
    retry_wait_s: float = 5.0,
) -> FetchResult:
    """Read ``name`` from the cache, else fetch it, and never raise.

    A missing map is a legitimate outcome -- it means the constraint disables
    itself for that route -- so a network failure has to come back as data the
    ablation can report rather than as an exception that ends the run.
    Endpoints are tried in order with ``retry_wait_s`` between them, and every
    failure is kept in the final message so the fetch table can print why.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{name}.json"

    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            return FetchResult(parse_overpass(blob, name=name), "cache", "", path,
                               path.stat().st_size)
        except (OSError, ValueError) as exc:
            return FetchResult(None, "error", f"unreadable cache {path}: {exc}", path)

    failures: list[str] = []
    for i, endpoint in enumerate(endpoints):
        if i > 0 and retry_wait_s > 0:
            time.sleep(retry_wait_s)
        try:
            return _fetch_one(name, endpoint, box, path, timeout_s)
        except (OSError, ValueError) as exc:
            failures.append(f"{endpoint}: {type(exc).__name__}: {exc}")

    return FetchResult(
        None, "error", "; ".join(failures) or "no endpoints configured", path
    )
