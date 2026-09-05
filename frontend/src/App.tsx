import { useEffect, useState } from "react";
import { loadSession, type Session } from "./data/session";
import { usePlayback } from "./state/usePlayback";
import { stateFromPyMode } from "./state/signalState";
import { OrbCanvas } from "./components/OrbCanvas";
import { RoutePanel } from "./components/RoutePanel";
import { Dashboard } from "./components/Dashboard";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSession()
      .then(setSession)
      .catch((e) => setError(String(e)));
  }, []);

  const { row, index } = usePlayback(session, 4); // 4x real-time so a full outage plays in ~25s

  if (error) {
    return <div style={{ padding: 24, color: "#E24DBE" }}>Failed to load session data: {error}</div>;
  }
  if (!session || !row) {
    return <div style={{ padding: 24, color: "#9FB3C8" }}>Loading replayed session…</div>;
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "320px 1fr",
        gridTemplateRows: "1fr 260px",
        height: "100vh",
        background: "#07090C",
        gap: 1,
      }}
    >
      <div style={{ gridRow: "1 / 3", padding: 20, overflow: "auto" }}>
        <Dashboard session={session} row={row} />
      </div>
      <div style={{ position: "relative", minHeight: 0 }}>
        <RoutePanel session={session} uptoIndex={index} />
        <div style={{ position: "absolute", top: 10, right: 10, width: 96, height: 96 }}>
          <OrbCanvas state={stateFromPyMode(row.mode)} />
        </div>
      </div>
      <div style={{ padding: "8px 16px", color: "#7C8A99", fontSize: 11, fontFamily: "ui-monospace, monospace" }}>
        ShadowNav web MVP — SIH26168. Real replayed data, synthetic outage (see banner). No real-world map yet
        (blueprint Step 8). Not affiliated with any real GNSS provider.
      </div>
    </div>
  );
}
