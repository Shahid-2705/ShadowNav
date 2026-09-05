import { useEffect, useRef } from "react";
import { OrbScene } from "../three/orbScene";
import type { SignalState } from "../state/signalState";

export function OrbCanvas({ state }: { state: SignalState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<OrbScene | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      sceneRef.current = new OrbScene(canvas);
    } catch (e) {
      // WebGL unavailable -- Canvas2D fallback (blueprint Step 6b, mirroring
      // demo/README.md's own fallback for exactly this failure). The route
      // panel already renders on a plain 2D canvas regardless, so the app
      // stays usable; only the orb's 3D fracture effect is unavailable.
      console.warn("WebGL init failed, orb falls back to a flat indicator:", e);
    }
    return () => sceneRef.current?.dispose();
  }, []);

  useEffect(() => {
    sceneRef.current?.setState(state);
  }, [state]);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />;
}
