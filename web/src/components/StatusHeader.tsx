/**
 * StatusHeader — title bar with per-component health lights (06-F10).
 *
 * Component states arrive as SystemStatus events on the same WebSocket as
 * everything else; the socket's own connectivity is the leftmost light.
 */

import type { SystemStatusEvent } from "../api/types";

const COMPONENTS = ["camera", "detector", "identifier", "speech", "cloudsync"] as const;

interface Props {
  connected: boolean;
  componentStatus: Record<string, SystemStatusEvent>;
}

function Light({ label, ok, detail }: { label: string; ok: boolean | null; detail?: string }) {
  const color = ok === null ? "bg-zinc-600" : ok ? "bg-emerald-400" : "bg-red-500";
  return (
    <span className="flex items-center gap-1.5 text-xs text-zinc-400" title={detail || label}>
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export function StatusHeader({ connected, componentStatus }: Props) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 pb-4">
      <h1 className="text-xl font-bold text-zinc-100">
        🎃 Costume Spotter
        <span className="ml-2 text-sm font-normal text-zinc-500">porch watch, live</span>
      </h1>
      <nav className="flex items-center gap-4">
        <Light label="link" ok={connected} detail="dashboard ↔ edge WebSocket" />
        {COMPONENTS.map((name) => {
          const status = componentStatus[name];
          return (
            <Light
              key={name}
              label={name}
              // null = no heartbeat yet (e.g. cloudsync disabled) → neutral grey
              ok={status ? status.ok : null}
              detail={status?.detail}
            />
          );
        })}
      </nav>
    </header>
  );
}
