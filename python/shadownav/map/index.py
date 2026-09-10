"""Grid-bucket spatial index over projected road segments.

A sequence's road network is a few thousand to a few tens of thousands of
polyline segments; the constraint asks "what lies within 30 m of here" ten
times a second. Bucketing segments into ~100 m cells makes that query touch a
handful of cells rather than the whole network, with nothing more exotic than
a dictionary -- there is no spatial library on the deployment target.

Each way contributes its polyline segments. A candidate is the nearest
segment of a way to the query point; two segments of the same way straddling
a vertex are collapsed to the nearer one, so the *disagreement* test in the
constraint compares distinct roads, not the two sides of one bend. Bends are
handled by the constraint's innovation gate instead.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .osm import ProjectedWay


@dataclass(frozen=True)
class Candidate:
    way_id: int
    highway: str
    oneway: int
    way_index: int
    seg_index: int
    distance_m: float
    along_m: float              # from the way's first node to the foot of the perpendicular
    bearing_fwd_rad: float      # bearing of the segment in node order, clockwise from north

    @property
    def bearings(self) -> tuple[float, ...]:
        """Travel bearings the vehicle may hold on this segment."""
        rev = math.atan2(math.sin(self.bearing_fwd_rad + math.pi), math.cos(self.bearing_fwd_rad + math.pi))
        if self.oneway == 1:
            return (self.bearing_fwd_rad,)
        if self.oneway == -1:
            return (rev,)
        return (self.bearing_fwd_rad, rev)


@dataclass(frozen=True, eq=False)
class RoadIndex:
    ways: tuple[ProjectedWay, ...]
    junction_nodes: frozenset[int]
    cell_m: float
    seg_way: np.ndarray
    seg_pos: np.ndarray
    e0: np.ndarray
    n0: np.ndarray
    e1: np.ndarray
    n1: np.ndarray
    bearing: np.ndarray
    cum_m: tuple[np.ndarray, ...]       # per way, along-way distance at each node
    buckets: dict[tuple[int, int], np.ndarray]

    @classmethod
    def build(cls, ways, junction_nodes: frozenset[int], cell_m: float = 100.0) -> "RoadIndex":
        ways = tuple(ways)
        seg_way, seg_pos, e0, n0, e1, n1, cum = [], [], [], [], [], [], []
        for wi, way in enumerate(ways):
            de = np.diff(way.east)
            dn = np.diff(way.north)
            step = np.hypot(de, dn)
            cum.append(np.concatenate([[0.0], np.cumsum(step)]))
            for si in np.flatnonzero(step > 1e-3):
                seg_way.append(wi)
                seg_pos.append(int(si))
                e0.append(way.east[si]); n0.append(way.north[si])
                e1.append(way.east[si + 1]); n1.append(way.north[si + 1])
        arrays = [np.asarray(a, dtype=float) for a in (e0, n0, e1, n1)]
        bearing = np.arctan2(arrays[2] - arrays[0], arrays[3] - arrays[1]) if seg_way else np.zeros(0)
        return cls(
            ways=ways, junction_nodes=junction_nodes, cell_m=float(cell_m),
            seg_way=np.asarray(seg_way, dtype=int), seg_pos=np.asarray(seg_pos, dtype=int),
            e0=arrays[0], n0=arrays[1], e1=arrays[2], n1=arrays[3], bearing=bearing,
            cum_m=tuple(cum), buckets=_bucket(arrays, float(cell_m)),
        )

    @property
    def n_segments(self) -> int:
        return int(self.seg_way.size)

    def _segments_near(self, east: float, north: float, radius_m: float) -> np.ndarray:
        c = self.cell_m
        ix0, ix1 = math.floor((east - radius_m) / c), math.floor((east + radius_m) / c)
        iy0, iy1 = math.floor((north - radius_m) / c), math.floor((north + radius_m) / c)
        hits = [self.buckets[(ix, iy)] for ix in range(ix0, ix1 + 1)
                for iy in range(iy0, iy1 + 1) if (ix, iy) in self.buckets]
        return np.unique(np.concatenate(hits)) if hits else np.zeros(0, dtype=int)

    def candidates(self, east: float, north: float, radius_m: float) -> tuple[Candidate, ...]:
        """Nearest segment of every way within ``radius_m``, nearest first."""
        idx = self._segments_near(east, north, radius_m)
        if idx.size == 0:
            return ()
        dx = self.e1[idx] - self.e0[idx]
        dy = self.n1[idx] - self.n0[idx]
        t = np.clip(((east - self.e0[idx]) * dx + (north - self.n0[idx]) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
        dist = np.hypot(east - (self.e0[idx] + t * dx), north - (self.n0[idx] + t * dy))
        best: dict[int, tuple[float, int, float]] = {}
        for k in np.flatnonzero(dist <= radius_m):
            wi = int(self.seg_way[idx[k]])
            if wi not in best or dist[k] < best[wi][0]:
                best[wi] = (float(dist[k]), int(idx[k]), float(t[k]))
        return tuple(sorted(
            (self._candidate(wi, seg, d, frac) for wi, (d, seg, frac) in best.items()),
            key=lambda c: c.distance_m,
        ))

    def _candidate(self, way_index: int, seg: int, distance: float, frac: float) -> Candidate:
        way = self.ways[way_index]
        pos = int(self.seg_pos[seg])
        cum = self.cum_m[way_index]
        along = float(cum[pos] + frac * (cum[pos + 1] - cum[pos]))
        return Candidate(way.way_id, way.highway, way.oneway, way_index, pos,
                         distance, along, float(self.bearing[seg]))

    def junction_ahead_m(self, cand: Candidate, forward: bool, lookahead_m: float) -> float:
        """Along-way distance to the first junction node ahead, or +inf."""
        way = self.ways[cand.way_index]
        cum = self.cum_m[cand.way_index]
        order = range(cand.seg_index + 1, len(way.node_ids)) if forward else range(cand.seg_index, -1, -1)
        for k in order:
            d = (cum[k] - cand.along_m) if forward else (cand.along_m - cum[k])
            if d > lookahead_m:
                break
            if way.node_ids[k] in self.junction_nodes:
                return float(max(d, 0.0))
        return math.inf


def _bucket(arrays: list[np.ndarray], cell_m: float) -> dict[tuple[int, int], np.ndarray]:
    e0, n0, e1, n1 = arrays
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k in range(e0.size):
        ix0, ix1 = sorted((math.floor(e0[k] / cell_m), math.floor(e1[k] / cell_m)))
        iy0, iy1 = sorted((math.floor(n0[k] / cell_m), math.floor(n1[k] / cell_m)))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                grid[(ix, iy)].append(k)
    return {key: np.asarray(v, dtype=int) for key, v in grid.items()}
