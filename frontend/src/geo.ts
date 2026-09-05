/**
 * WGS84 local tangent-plane projection, matching python/shadownav/geo.py's
 * `curvature_radii`/`lla_to_enu` exactly (same constants, same formula) so
 * a point plotted here lands at the same local coordinate the Python
 * pipeline that produced session.json would compute -- not a second,
 * divergent projection.
 */
const WGS84_A = 6378137.0;
const WGS84_F = 1.0 / 298.257223563;
const WGS84_E2 = WGS84_F * (2.0 - WGS84_F);

export function curvatureRadii(latDeg: number): { meridional: number; normal: number } {
  const s = Math.sin((latDeg * Math.PI) / 180);
  const denom = 1.0 - WGS84_E2 * s * s;
  const meridional = (WGS84_A * (1.0 - WGS84_E2)) / Math.pow(denom, 1.5);
  const normal = WGS84_A / Math.sqrt(denom);
  return { meridional, normal };
}

export function llaToEnu(latDeg: number, lonDeg: number, refLatDeg: number, refLonDeg: number) {
  const { meridional, normal } = curvatureRadii(refLatDeg);
  const north = (((latDeg - refLatDeg) * Math.PI) / 180) * meridional;
  const east =
    (((lonDeg - refLonDeg) * Math.PI) / 180) * normal * Math.cos((refLatDeg * Math.PI) / 180);
  return { east, north };
}
