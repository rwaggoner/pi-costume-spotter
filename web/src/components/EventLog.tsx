/**
 * EventLog — the scrolling live feed of what the system is doing (06-F7).
 * Newest first; the hook caps the list, so rendering it all is fine.
 */

import type { LogEntry } from "../hooks/useEventSocket";

const KIND_ICONS: Record<string, string> = {
  NewVisitorSpotted: "👀",
  CostumeIdentified: "🎃",
  SightingLogged: "💾",
  CommentSpoken: "🔊",
};

export function EventLog({ log }: { log: LogEntry[] }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-zinc-800 bg-zinc-900">
      <h2 className="border-b border-zinc-800 px-4 py-2 text-sm font-semibold text-zinc-300">
        Live events
      </h2>
      <ol className="flex-1 space-y-1 overflow-y-auto p-3 text-sm">
        {log.length === 0 && (
          <li className="text-zinc-500">Waiting for the first visitor…</li>
        )}
        {log.map((entry) => (
          <li key={entry.id} className="flex gap-2 text-zinc-300">
            <span className="shrink-0">{KIND_ICONS[entry.kind] ?? "•"}</span>
            <span className="shrink-0 font-mono text-xs text-zinc-500">
              {new Date(entry.timestamp).toLocaleTimeString()}
            </span>
            <span className="min-w-0 break-words">{entry.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
