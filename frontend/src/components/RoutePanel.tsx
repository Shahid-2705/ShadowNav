/**
 * The route plane: aided/dead-reckoned trails, the calibrated confidence
 * ring, and the vehicle marker -- the web equivalent of Android's
 * `TrackView`/`MapRouteView` (blueprint Step 6b/7), drawn on a plain 2D
 * canvas over an auto-scaled local-metre projection. This is deliberately
 * NOT a real map yet: MapLibre GL JS + real basemap tiles is blueprint
 * Step 8, a separate, not-yet-done step. Colours match Android's
 * `Ui.kt` `Palette` and the demo's `COL` exactly.
 */
import { useEffect, useRef } from "react";
import { llaToEnu } from "../geo";
import type { Session } from "../data/session";
import { stateFromPyMode } from "../state/signalState";

const CYAN = "#4DE0E8";
const MAGENTA = "#E24DBE";
const AMBER = "#E8A33D";
const SLATE = "#8492A1";
const BG = "#07090C";

export function RoutePanel({ session, uptoIndex }: { session: Session; uptoIndex: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio, 2);
    const { clientWidth: w, clientHeight: h } = canvas;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, w, h);

    const rows = session.rows.slice(0, uptoIndex + 1);
    if (rows.length === 0) return;

    const pts = rows.map((r) => llaToEnu(r.estLat, r.estLon, session.refLat, session.refLon));
    const truthPts = rows
      .filter((r) => r.truthLat !== null && r.truthLon !== null)
      .map((r) => llaToEnu(r.truthLat as number, r.truthLon as number, session.refLat, session.refLon));

    let minE = Infinity, maxE = -Infinity, minN = Infinity, maxN = -Infinity;
    for (const p of [...pts, ...truthPts]) {
      minE = Math.min(minE, p.east); maxE = Math.max(maxE, p.east);
      minN = Math.min(minN, p.north); maxN = Math.max(maxN, p.north);
    }
    const spanM = Math.max(maxE - minE, maxN - minN, 40);
    const pad = 30;
    const scale = (Math.min(w, h) - 2 * pad) / spanM;
    const cx = (minE + maxE) / 2;
    const cy = (minN + maxN) / 2;
    const sx = (e: number) => w / 2 + (e - cx) * scale;
    const sy = (n: number) => h / 2 - (n - cy) * scale;

    // 100m grid, same convention as Android's TrackView
    ctx.strokeStyle = "#1B2530";
    ctx.lineWidth = 1;
    const step = 100 * scale;
    if (step > 24) {
      for (let g = (w / 2) % step; g < w; g += step) {
        ctx.beginPath(); ctx.moveTo(g, 0); ctx.lineTo(g, h); ctx.stroke();
      }
      for (let g = (h / 2) % step; g < h; g += step) {
        ctx.beginPath(); ctx.moveTo(0, g); ctx.lineTo(w, g); ctx.stroke();
      }
    }

    ctx.strokeStyle = SLATE + "88";
    ctx.lineWidth = 2;
    ctx.beginPath();
    truthPts.forEach((p, i) => (i === 0 ? ctx.moveTo(sx(p.east), sy(p.north)) : ctx.lineTo(sx(p.east), sy(p.north))));
    ctx.stroke();

    // Aided (cyan) vs dead-reckoned/reacquiring (magenta/amber) segments
    let currentColor: string | null = null;
    ctx.lineWidth = 3;
    for (let i = 1; i < rows.length; i++) {
      const state = stateFromPyMode(rows[i].mode);
      const color =
        state === "AIDED" ? CYAN : state === "REACQUIRING" ? AMBER : MAGENTA;
      if (color !== currentColor) {
        ctx.beginPath();
        ctx.moveTo(sx(pts[i - 1].east), sy(pts[i - 1].north));
        currentColor = color;
        ctx.strokeStyle = color;
      }
      ctx.lineTo(sx(pts[i].east), sy(pts[i].north));
      ctx.stroke();
    }

    const cur = rows[rows.length - 1];
    const curPt = pts[pts.length - 1];
    if (cur.radius90m) {
      ctx.strokeStyle = AMBER + "99";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(sx(curPt.east), sy(curPt.north), cur.radius90m * scale, 0, Math.PI * 2);
      ctx.stroke();
    }

    // vehicle chevron
    const state = stateFromPyMode(cur.mode);
    const chevColor = state === "AIDED" ? CYAN : state === "REACQUIRING" ? AMBER : MAGENTA;
    const hx = sx(curPt.east), hy = sy(curPt.north);
    const h2 = cur.headingRad;
    const dx = Math.sin(h2), dz = -Math.cos(h2);
    const size = 12;
    ctx.fillStyle = chevColor;
    ctx.beginPath();
    ctx.moveTo(hx + dx * size, hy + dz * size);
    ctx.lineTo(hx - dz * size * 0.6 - dx * size * 0.5, hy + dx * size * 0.6 - dz * size * 0.5);
    ctx.lineTo(hx + dz * size * 0.6 - dx * size * 0.5, hy - dx * size * 0.6 - dz * size * 0.5);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#7C8A99";
    ctx.font = "12px ui-monospace, monospace";
    ctx.fillText("grid 100 m · no basemap yet (blueprint Step 8)", 10, h - 10);
  }, [session, uptoIndex]);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />;
}
