"""Heading-only OpenStreetMap constraint.

The problem statement asks for a "Map-Matching Framework ... offline road
networks (OpenStreetMap) using kinematic constraints". This package builds the
narrow, defensible form of that, per
``research/SIH26168-open-track-findings.md`` Track C:

* the road's **bearing** enters the filter as a heading observation
  (Fouque, Bonnifait & Bétaille, IEEE/ION PLANS 2008 -- *map-aided odometry*;
  name it before a judge does, it is not novel);
* **lateral position is never constrained.** On parallel service roads beside a
  highway -- the classic ambiguity -- the bearing is identical across
  candidates, so a heading constraint is safe exactly where a position
  constraint is most dangerous;
* the constraint **self-disables** rather than guessing: no candidate within
  200 m (Newson & Krumm's rule, which is what happens in a tunnel or a
  multi-storey car park, where OSM has no network at all), candidates that
  disagree on bearing, a junction inside the lookahead, or an innovation the
  chi-square gate rejects.

Nothing here can fix the dominant error on IO-VNBD, which is along-track and
comes from stale speed. Cross-track error is the metric this attacks.
"""

from . import heading_constraint, index, osm

__all__ = ["heading_constraint", "index", "osm"]
