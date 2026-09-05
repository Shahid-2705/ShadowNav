/**
 * Icosphere shard-fracture geometry, ported from demo/gnss-demo.html's
 * `buildIcosphere` / `faceAdjacency` / `clusterFaces` / `buildShardSet`
 * (blueprint Step 6b). The demo's own math is framework-agnostic (pure
 * vector geometry), so this is a faithful line-for-line port to TypeScript,
 * not a reinterpretation -- only the GL plumbing around it (buffers,
 * shaders) is re-expressed in Three.js idiom in orbScene.ts.
 *
 * Region-growing: pick K farthest-point seed faces, then a randomized
 * multi-source Dijkstra over face adjacency grows each seed into an
 * irregular polygonal panel (a "shard"). Each shard becomes its own small
 * mesh (outer skin + inner skin + boundary wall) so it can be exploded
 * outward independently during a blackout and reassembled on reacquisition.
 */

export type Vec3 = [number, number, number];

function v3norm(a: Vec3): Vec3 {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
}
function v3add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}
function v3sub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function v3scale(a: Vec3, s: number): Vec3 {
  return [a[0] * s, a[1] * s, a[2] * s];
}
function v3dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
function v3cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
/** Deterministic PRNG (mulberry32), matching the demo's own -- same seed,
 *  same shard layout, every run and on every platform. */
export function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Icosphere {
  V: Vec3[];
  F: number[][];
}

function buildIcosphere(subdiv: number): Icosphere {
  const t = (1 + Math.sqrt(5)) / 2;
  let V: Vec3[] = (
    [
      [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
      [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
      [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
    ] as Vec3[]
  ).map(v3norm);
  let F: number[][] = [
    [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
    [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
    [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
    [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
  ];
  for (let s = 0; s < subdiv; s++) {
    const cache = new Map<string, number>();
    const nf: number[][] = [];
    const mid = (a: number, b: number): number => {
      const k = a < b ? `${a}_${b}` : `${b}_${a}`;
      const cached = cache.get(k);
      if (cached !== undefined) return cached;
      V.push(v3norm(v3scale(v3add(V[a], V[b]), 0.5)));
      const idx = V.length - 1;
      cache.set(k, idx);
      return idx;
    };
    for (const f of F) {
      const a = mid(f[0], f[1]);
      const b = mid(f[1], f[2]);
      const c = mid(f[2], f[0]);
      nf.push([f[0], a, c], [f[1], b, a], [f[2], c, b], [a, b, c]);
    }
    F = nf;
  }
  for (const f of F) {
    const n = v3cross(v3sub(V[f[1]], V[f[0]]), v3sub(V[f[2]], V[f[0]]));
    if (v3dot(n, V[f[0]]) < 0) {
      const tmp = f[1];
      f[1] = f[2];
      f[2] = tmp;
    }
  }
  return { V, F };
}

function faceAdjacency(F: number[][]): number[][] {
  const edgeMap = new Map<string, number>();
  const adj: number[][] = F.map(() => []);
  F.forEach((f, i) => {
    for (let e = 0; e < 3; e++) {
      const a = f[e];
      const b = f[(e + 1) % 3];
      const k = a < b ? `${a}_${b}` : `${b}_${a}`;
      const existing = edgeMap.get(k);
      if (existing !== undefined) {
        adj[i].push(existing);
        adj[existing].push(i);
      } else {
        edgeMap.set(k, i);
      }
    }
  });
  return adj;
}

function clusterFaces(V: Vec3[], F: number[][], adj: number[][], K: number, r: () => number): number[][] {
  const C: Vec3[] = F.map((f) => v3norm(v3add(v3add(V[f[0]], V[f[1]]), V[f[2]])));
  const seeds = [Math.floor(r() * F.length)];
  const best = C.map(() => Infinity);
  while (seeds.length < K) {
    const s = seeds[seeds.length - 1];
    let far = -1;
    let farD = -1;
    for (let i = 0; i < F.length; i++) {
      const d = 1 - v3dot(C[i], C[s]);
      if (d < best[i]) best[i] = d;
      if (best[i] > farD) {
        farD = best[i];
        far = i;
      }
    }
    seeds.push(far);
  }
  const owner = new Int32Array(F.length).fill(-1);
  const dist = new Float64Array(F.length).fill(Infinity);
  type HeapEntry = [number, number, number];
  const heap: HeapEntry[] = [];
  const push = (d: number, i: number, o: number) => {
    heap.push([d, i, o]);
    let k = heap.length - 1;
    while (k > 0) {
      const p = (k - 1) >> 1;
      if (heap[p][0] <= heap[k][0]) break;
      [heap[p], heap[k]] = [heap[k], heap[p]];
      k = p;
    }
  };
  const pop = (): HeapEntry => {
    const top = heap[0];
    const last = heap.pop() as HeapEntry;
    if (heap.length) {
      heap[0] = last;
      let k = 0;
      for (;;) {
        const l = 2 * k + 1;
        const rr = l + 1;
        let m = k;
        if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
        if (rr < heap.length && heap[rr][0] < heap[m][0]) m = rr;
        if (m === k) break;
        [heap[m], heap[k]] = [heap[k], heap[m]];
        k = m;
      }
    }
    return top;
  };
  seeds.forEach((s, o) => {
    dist[s] = 0;
    push(0, s, o);
  });
  while (heap.length) {
    const [d, i, o] = pop();
    if (owner[i] !== -1) continue;
    owner[i] = o;
    for (const j of adj[i]) {
      if (owner[j] !== -1) continue;
      const nd = d + 0.55 + r() * 0.9;
      if (nd < dist[j]) {
        dist[j] = nd;
        push(nd, j, o);
      }
    }
  }
  const groups: number[][] = Array.from({ length: K }, () => []);
  owner.forEach((o, i) => groups[o].push(i));
  return groups.filter((g) => g.length > 0);
}

const R_OUT = 1.0;
const R_IN = 0.93;

export interface Shard {
  /** Interleaved pos3+normal3 per vertex, in the shard's own local frame
   *  (relative to its rest center) -- matches the demo's VSTRIDE=8 layout
   *  minus edgeDist/kind, which the web port doesn't need (no seam shader
   *  here; Three.js MeshPhysicalMaterial + emissive carries the look). */
  positions: Float32Array;
  normals: Float32Array;
  nVerts: number;
  /** Rest center of the shard on the unit sphere (unexploded position). */
  center: Vec3;
  dir: Vec3;
  /** Deterministic outward+tangential impulse direction (unit-ish). */
  impulse: Vec3;
  axis: Vec3;
  spin: number;
  drift: number;
  sag: number;
  phase: number;
}

export function buildShardSet(subdiv: number, K: number, seed: number): Shard[] {
  const r = mulberry32(seed);
  const { V, F } = buildIcosphere(subdiv);
  const adj = faceAdjacency(F);
  const groups = clusterFaces(V, F, adj, K, r);
  const shards: Shard[] = [];

  for (const g of groups) {
    const edgeCount = new Map<string, number>();
    const verts = new Set<number>();
    for (const fi of g) {
      const f = F[fi];
      for (let e = 0; e < 3; e++) {
        const a = f[e];
        const b = f[(e + 1) % 3];
        verts.add(a);
        const k = a < b ? `${a}_${b}` : `${b}_${a}`;
        edgeCount.set(k, (edgeCount.get(k) || 0) + 1);
      }
    }
    let cen: Vec3 = [0, 0, 0];
    for (const vi of verts) cen = v3add(cen, V[vi]);
    const dir = v3norm(cen);
    const rMid = (R_OUT + R_IN) / 2;
    const center = v3scale(dir, rMid);

    const positions: number[] = [];
    const normals: number[] = [];
    const emit = (p: Vec3, n: Vec3) => {
      const rel = v3sub(p, center);
      positions.push(rel[0], rel[1], rel[2]);
      normals.push(n[0], n[1], n[2]);
    };
    for (const fi of g) {
      const f = F[fi];
      for (const vi of f) emit(v3scale(V[vi], R_OUT), V[vi]); // outer skin
      for (const vi of [f[0], f[2], f[1]]) emit(v3scale(V[vi], R_IN), v3scale(V[vi], -1)); // inner skin
    }
    // boundary wall quads
    const boundary: [number, number][] = [];
    for (const fi of g) {
      const f = F[fi];
      for (let e = 0; e < 3; e++) {
        const a = f[e];
        const b = f[(e + 1) % 3];
        const k = a < b ? `${a}_${b}` : `${b}_${a}`;
        if (edgeCount.get(k) === 1) boundary.push([a, b]);
      }
    }
    for (const [a, b] of boundary) {
      const oa = v3scale(V[a], R_OUT);
      const ob = v3scale(V[b], R_OUT);
      const ia = v3scale(V[a], R_IN);
      const ib = v3scale(V[b], R_IN);
      let n = v3norm(v3cross(v3sub(ob, oa), v3sub(ib, oa)));
      let tri: Vec3[] = [oa, ob, ib, oa, ib, ia];
      const mid = v3scale(v3add(oa, ob), 0.5);
      if (v3dot(n, v3sub(mid, center)) < 0) {
        n = v3scale(n, -1);
        tri = [oa, ib, ob, oa, ia, ib];
      }
      for (const p of tri) emit(p, n);
    }

    const up: Vec3 = Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
    const t1 = v3norm(v3cross(up, dir));
    const t2 = v3cross(dir, t1);
    const ang = r() * Math.PI * 2;
    const radMag = 0.75 + r() * 0.75;
    const tanMag = 0.18 + r() * 0.3;
    const impulse = v3add(
      v3scale(dir, radMag),
      v3add(v3scale(t1, Math.cos(ang) * tanMag), v3scale(t2, Math.sin(ang) * tanMag)),
    );
    const axis = v3norm([r() * 2 - 1, r() * 2 - 1, r() * 2 - 1]);

    shards.push({
      positions: new Float32Array(positions),
      normals: new Float32Array(normals),
      nVerts: positions.length / 3,
      center,
      dir,
      impulse,
      axis,
      spin: (r() * 2 - 1) * 2.4,
      drift: (r() * 2 - 1) * 0.35,
      sag: 0.45 + r() * 0.35,
      phase: r() * Math.PI * 2,
    });
  }
  return shards;
}

/** Closed-form shard trajectory as a function of the fracture clock tau --
 *  impulse under viscous damping K_DAMP, gravity fading under K_GRAV so the
 *  cloud hangs instead of falling, ported exactly from the demo's
 *  `packShards` (blueprint Step 6b). Fully reversible: scrubbing tau
 *  backwards during a REACQUIRING ease-out reverses this exactly, the same
 *  property the demo relies on for interrupt-safe transitions. */
const K_DAMP = 1.8;
const K_GRAV = 1.4;
const G0 = -0.55;

export function shardOffsetAt(shard: Shard, tau: number): Vec3 {
  const e1 = (1 - Math.exp(-K_DAMP * tau)) / K_DAMP;
  const gravTerm = (G0 * ((1 - Math.exp(-K_GRAV * tau)) / K_GRAV - e1)) / (K_DAMP - K_GRAV);
  const env = 1 - Math.exp(-K_DAMP * tau);
  const local: Vec3 = [
    shard.impulse[0] * e1,
    shard.impulse[1] * e1 + gravTerm * shard.sag + 0.025 * Math.sin(0.9 * tau + shard.phase) * env,
    shard.impulse[2] * e1,
  ];
  return local;
}

export function shardSpinAt(shard: Shard, tau: number): number {
  const e1 = (1 - Math.exp(-K_DAMP * tau)) / K_DAMP;
  return shard.spin * e1 + shard.drift * tau;
}
