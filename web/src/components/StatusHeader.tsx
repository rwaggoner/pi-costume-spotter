/**
 * StatusHeader — title bar with per-component health lights (06-F10).
 *
 * Component states arrive as SystemStatus events on the same WebSocket as
 * everything else; the socket's own connectivity is the leftmost light.
 */

import type { SystemStatusEvent } from "../api/types";
import type { Page } from "../App";
import { ResetButton } from "./ResetButton";

const COMPONENTS = ["camera", "detector", "identifier", "speech", "cloudsync"] as const;

interface Props {
  connected: boolean;
  componentStatus: Record<string, SystemStatusEvent>;
  page: Page;
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

const TABS: { page: Page; href: string; label: string }[] = [
  { page: "live", href: "#/", label: "Live" },
  { page: "stats", href: "#/stats", label: "Stats" },
];

export function StatusHeader({ connected, componentStatus, page }: Props) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 pb-4">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-bold text-zinc-100">🎃 Costume Spotter</h1>
        <nav aria-label="Pages" className="flex gap-1">
          {TABS.map((tab) => (
            <a
              key={tab.page}
              href={tab.href}
              aria-current={page === tab.page ? "page" : undefined}
              className={`rounded-md px-3 py-1 text-sm ${page === tab.page
                ? "bg-zinc-800 font-semibold text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}
            >
              {tab.label}
            </a>
          ))}
        </nav>
      </div>
      <div className="flex flex-wrap items-center gap-4">
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
        <ResetButton />
      </div>
    </header>
  );
}
