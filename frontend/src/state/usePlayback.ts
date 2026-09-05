import { useEffect, useRef, useState } from "react";
import type { Session } from "../data/session";

/**
 * Steps through a loaded [Session]'s rows by elapsed wall-clock time at a
 * fixed rate. Deterministic in the sense that matters here: the same
 * session always produces the same sequence of rows in the same order --
 * full bit-for-bit frame determinism (the demo's fixed 100Hz-step property)
 * isn't meaningful for replaying already-computed data, only for a live
 * simulation, so this hook doesn't reproduce that specific guarantee.
 */
export function usePlayback(session: Session | null, rate = 1) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const lastRef = useRef<number | null>(null);
  const tRef = useRef(0);

  useEffect(() => {
    if (!session || !playing) return;
    let raf = 0;
    const tick = (now: number) => {
      if (lastRef.current === null) lastRef.current = now;
      const dt = ((now - lastRef.current) / 1000) * rate;
      lastRef.current = now;
      tRef.current += dt;
      const rows = session.rows;
      const last = rows[rows.length - 1].t;
      if (tRef.current > last) tRef.current = 0; // loop the replay
      let lo = 0;
      let hi = rows.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (rows[mid].t <= tRef.current) lo = mid;
        else hi = mid - 1;
      }
      setIndex(lo);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [session, playing, rate]);

  const seek = (t: number) => {
    tRef.current = t;
    lastRef.current = null;
  };

  return {
    row: session?.rows[index] ?? null,
    index,
    playing,
    setPlaying,
    seek,
  };
}
