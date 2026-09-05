import type { Session, SessionRow } from "../data/session";
import { STATE_LABEL, stateFromPyMode } from "../state/signalState";

export function Dashboard({ session, row }: { session: Session; row: SessionRow }) {
  const state = stateFromPyMode(row.mode);
  return (
    <div style={{ fontFamily: "ui-monospace, monospace", color: "#DCE6F0", fontSize: 13, lineHeight: 1.6 }}>
      <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "0.04em" }}>ShadowNav — web MVP</div>
      <div style={{ color: "#7C8A99", marginBottom: 12 }}>
        {session.session} · {session.fold} fold · t={row.t.toFixed(1)}s
      </div>

      <div
        style={{
          background: "#3D2A0E",
          border: "1px solid #E8A33D55",
          color: "#E8A33D",
          padding: "8px 12px",
          borderRadius: 8,
          marginBottom: 12,
          fontSize: 12,
        }}
      >
        SYNTHETIC OUTAGE — {session.note}
      </div>

      <div style={{ fontSize: 18, marginBottom: 4 }}>{STATE_LABEL[state]}</div>
      <div>90% radius: {row.radius90m !== null ? `${row.radius90m.toFixed(0)} m` : "--"}</div>
      <div>speed: {(row.speedMs * 3.6).toFixed(0)} km/h</div>
      <div>
        outage: {session.outageStartS}s + {session.outageDurationS}s · distance {session.distanceM} m
      </div>
      <div style={{ marginTop: 12, color: "#7C8A99", fontSize: 11 }}>
        conformal λ = {session.conformalLambda.toFixed(2)} at {session.conformalLevel * 100}% level
        <br />
        source: {session.source}
      </div>
    </div>
  );
}
