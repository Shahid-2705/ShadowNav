/**
 * The status orb scene: a Filament-orb-equivalent for the web, built the
 * same way `demo/gnss-demo.html` builds its signal orb -- a shattered
 * icosphere whose shards explode outward under a fracture clock (tau) and
 * reassemble on reacquisition (blueprint Step 6b). Bloom uses Three.js's
 * own `UnrealBloomPass` rather than the demo's hand-rolled two-pass
 * separable blur -- same technique (bright-pass extract + blur + additive
 * composite), a maintained library implementation instead of a port of the
 * raw GLSL, which is the appropriate trade for "componentized, reviewable
 * modules" rather than a byte-for-byte translation of 1400 lines of
 * hand-tuned WebGL.
 *
 * Tier system mirrors the demo's HIGH/LOW split (`demo/README.md`,
 * `TIER_PARAMS`): HIGH = subdiv 2 / 84 shards, LOW = subdiv 1 / 36 shards,
 * with LOW picked automatically if the first several frames measure slow.
 */
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { buildShardSet, shardOffsetAt, shardSpinAt, type Shard } from "./icosphereShards";
import type { SignalState } from "../state/signalState";
import { PALETTE_TARGETS, mixColor, type Palette } from "../state/palette";

export type RenderTier = "HIGH" | "LOW";

const TIER_PARAMS: Record<RenderTier, { subdiv: number; K: number }> = {
  HIGH: { subdiv: 2, K: 84 },
  LOW: { subdiv: 1, K: 36 },
};

const SEED = 20260905; // same seed as the demo, for the same reason: reproducible, comparable runs
const K_DAMP_TAU_RATE = 1; // tau advances 1:1 with seconds in BLACKOUT, matches demo

interface ShardMesh {
  shard: Shard;
  mesh: THREE.Mesh;
}

export class OrbScene {
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private shardMeshes: ShardMesh[] = [];
  private material: THREE.MeshStandardMaterial;
  private tau = 0;
  private seam = 0;
  private palette: Palette;
  private tier: RenderTier;
  private frameTimes: number[] = [];
  private disposed = false;
  private state: SignalState = "ACQUIRING";
  private raf = 0;
  private canvas: HTMLCanvasElement;

  constructor(canvas: HTMLCanvasElement, tier: RenderTier = "HIGH") {
    this.canvas = canvas;
    this.tier = tier;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setClearColor(0x07090c, 1);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));

    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 20);
    this.camera.position.set(0, 0.15, 3.4);
    this.camera.lookAt(0, 0, 0);

    this.scene.add(new THREE.HemisphereLight(0x8fb8ff, 0x0a0d12, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(-0.55, 0.85, 0.55);
    this.scene.add(key);

    this.material = new THREE.MeshStandardMaterial({
      color: 0x84929e,
      emissive: 0x84929e,
      emissiveIntensity: 0.15,
      roughness: 0.35,
      metalness: 0.1,
    });
    this.palette = { ...PALETTE_TARGETS.ACQUIRING };
    this.buildShards();

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.9, 0.6, 0.15);
    this.composer.addPass(bloom);
    this.composer.addPass(new OutputPass());

    this.resize();
    window.addEventListener("resize", this.resize);
    this.raf = requestAnimationFrame(this.tick);
  }

  private buildShards() {
    for (const { mesh } of this.shardMeshes) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();
    }
    this.shardMeshes = [];
    const shards = buildShardSet(TIER_PARAMS[this.tier].subdiv, TIER_PARAMS[this.tier].K, SEED);
    for (const shard of shards) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(shard.positions, 3));
      geo.setAttribute("normal", new THREE.BufferAttribute(shard.normals, 3));
      const mesh = new THREE.Mesh(geo, this.material);
      mesh.position.set(shard.center[0], shard.center[1], shard.center[2]);
      this.scene.add(mesh);
      this.shardMeshes.push({ shard, mesh });
    }
  }

  /** Push a new state; the palette eases toward it over subsequent frames
   *  (never a hard cut) the same way the demo's `stepPalette` does. */
  setState(state: SignalState) {
    this.state = state;
  }

  private resize = () => {
    const { clientWidth: w, clientHeight: h } = this.canvas;
    if (w === 0 || h === 0) return;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  };

  private lastT = performance.now();

  private tick = (now: number) => {
    if (this.disposed) return;
    const dt = Math.min(0.1, (now - this.lastT) / 1000);
    this.lastT = now;
    this.step(dt);
    const t0 = performance.now();
    this.composer.render();
    const frameMs = performance.now() - t0;
    this.trackFrameTime(frameMs);
    this.raf = requestAnimationFrame(this.tick);
  };

  private trackFrameTime(ms: number) {
    if (this.tier === "LOW") return; // already at the floor
    this.frameTimes.push(ms);
    if (this.frameTimes.length < 60) return;
    const over = this.frameTimes.filter((f) => f > 22).length;
    this.frameTimes = [];
    // Mirrors demo/README.md's own auto-degrade rule: too many frames over
    // 22ms in a row drops the tier, and the shard set only swaps when the
    // orb is whole (tau ~ 0) so the re-tiling is invisible -- see the
    // reason that rule exists (demo/README.md "Performance and fallbacks").
    if (over > 45 && this.tau < 0.05) {
      this.tier = "LOW";
      this.buildShards();
    }
  }

  private step(dt: number) {
    const target = PALETTE_TARGETS[this.state];
    const k = Math.min(1, dt * (this.state === "REACQUIRING" ? 14 : 6));
    this.palette = mixColor(this.palette, target, k);

    const isBlackout = this.state === "DEAD_RECKONING" || this.state === "SIMULATED_BLACKOUT";
    if (isBlackout) {
      this.tau += dt * K_DAMP_TAU_RATE;
    } else if (this.state === "REACQUIRING") {
      // scrub back with the same ease-out the demo uses, never a hard reset
      this.tau = Math.max(0, this.tau - dt * (this.tau / 1.8 + 0.4));
    } else {
      this.tau = Math.max(0, this.tau - dt * 4);
    }
    const seamTarget = this.state === "ACQUIRING" || this.state === "AIDED" ? 0 : isBlackout ? 1 : 0.5;
    this.seam += (seamTarget - this.seam) * Math.min(1, dt * 6);

    this.material.color.setRGB(...this.palette.core);
    this.material.emissive.setRGB(...this.palette.core);
    this.material.emissiveIntensity = this.palette.coreI;

    const yaw = performance.now() * 0.00006;
    for (const { shard, mesh } of this.shardMeshes) {
      const offset = shardOffsetAt(shard, this.tau);
      const spin = shardSpinAt(shard, this.tau);
      mesh.position.set(
        shard.center[0] + offset[0],
        shard.center[1] + offset[1],
        shard.center[2] + offset[2],
      );
      mesh.setRotationFromAxisAngle(
        new THREE.Vector3(shard.axis[0], shard.axis[1], shard.axis[2]),
        spin,
      );
      mesh.rotateY(0); // orientation baked into position path; kept for future per-shard spin refinement
    }
    this.scene.rotation.y = yaw;
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this.resize);
    for (const { mesh } of this.shardMeshes) mesh.geometry.dispose();
    this.material.dispose();
    this.renderer.dispose();
  }
}
