/**
 * The same six states as android/app/.../UiSignalState.kt, by name --
 * "read as one product" across Android, web and the demo (Ui.kt's own
 * file comment). The exported session's `mode` field uses Python's
 * GnssMode enum values (shadownav.core / shadownav.filter.fsm), mapped
 * here 1:1 rather than re-deriving a parallel vocabulary.
 */
export type SignalState =
  | "ACQUIRING"
  | "SIMULATED_BLACKOUT"
  | "AIDED"
  | "DEGRADED"
  | "REACQUIRING"
  | "DEAD_RECKONING";

const PY_MODE_TO_STATE: Record<string, SignalState> = {
  GNSS_AIDED: "AIDED",
  AIDED: "AIDED",
  DEGRADED: "DEGRADED",
  DEAD_RECKONING: "DEAD_RECKONING",
  REACQUIRING: "REACQUIRING",
};

export function stateFromPyMode(mode: string): SignalState {
  return PY_MODE_TO_STATE[mode] ?? "ACQUIRING";
}

export const STATE_LABEL: Record<SignalState, string> = {
  ACQUIRING: "ACQUIRING",
  SIMULATED_BLACKOUT: "SIMULATED BLACKOUT",
  AIDED: "GNSS AIDED",
  DEGRADED: "DEGRADED",
  REACQUIRING: "REACQUIRING",
  DEAD_RECKONING: "DEAD RECKONING",
};
