/**
 * Colour targets per [SignalState], ported from demo/gnss-demo.html's
 * `paletteTarget()` / `COL` and matching Android's `Ui.kt` `Palette`
 * object exactly (same hex values) so all three surfaces read as one
 * product.
 */
import type { SignalState } from "./signalState";

export type RGB = [number, number, number];

export interface Palette {
  core: RGB;
  coreI: number;
}

// Matches Ui.kt: CYAN 0x4DE0E8, AMBER 0xE8A33D, MAGENTA 0xE24DBE, SLATE 0x8492A1
const CYAN: RGB = [0x4d / 255, 0xe0 / 255, 0xe8 / 255];
const AMBER: RGB = [0xe8 / 255, 0xa3 / 255, 0x3d / 255];
const MAGENTA: RGB = [0xe2 / 255, 0x4d / 255, 0xbe / 255];
const SLATE: RGB = [0x84 / 255, 0x92 / 255, 0xa1 / 255];

export const PALETTE_TARGETS: Record<SignalState, Palette> = {
  ACQUIRING: { core: SLATE, coreI: 0.12 },
  AIDED: { core: CYAN, coreI: 0.9 },
  DEGRADED: { core: AMBER, coreI: 0.75 },
  REACQUIRING: { core: AMBER, coreI: 0.6 },
  SIMULATED_BLACKOUT: { core: MAGENTA, coreI: 0.35 },
  DEAD_RECKONING: { core: MAGENTA, coreI: 0.35 },
};

export function mixColor(a: Palette, b: Palette, t: number): Palette {
  return {
    core: [
      a.core[0] + (b.core[0] - a.core[0]) * t,
      a.core[1] + (b.core[1] - a.core[1]) * t,
      a.core[2] + (b.core[2] - a.core[2]) * t,
    ],
    coreI: a.coreI + (b.coreI - a.coreI) * t,
  };
}
