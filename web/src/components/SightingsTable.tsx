/**
 * SightingsTable — persisted history with snapshot thumbnails (06-F8).
 * Data comes from REST (useSightings); snapshots load lazily per row.
 */

import { api } from "../api/client";
import type { Sighting } from "../api/types";

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "text-emerald-400",
  medium: "text-amber-400",
  low: "text-orange-400",
  unknown: "text-zinc-500",
};

export function SightingsTable({ sightings }: { sightings: Sighting[] }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <h2 className="border-b border-zinc-800 px-4 py-2 text-sm font-semibold text-zinc-300">
        Sighting history
      </h2>
      {sightings.length === 0 ? (
        <p className="p-4 text-sm text-zinc-500">No sightings yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase text-zinc-500">
              <th className="px-4 py-2">Snapshot</th>
              <th className="px-4 py-2">Costume</th>
              <th className="px-4 py-2">Comment</th>
              <th className="px-4 py-2">When</th>
              <th className="px-4 py-2">Spoken</th>
            </tr>
          </thead>
          <tbody>
            {sightings.map((s) => (
              <tr key={s.id} className="border-b border-zinc-800/50 align-top text-zinc-300">
                <td className="px-4 py-2">
                  {s.has_snapshot ? (
                    <img
                      src={api.snapshotUrl(s.id)}
                      alt={s.costume ?? "visitor"}
                      loading="lazy"
                      className="h-14 w-14 rounded object-cover"
                    />
                  ) : (
                    <span className="text-zinc-600">—</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <div className="font-medium">{s.costume ?? "no costume"}</div>
                  <div className={`text-xs ${CONFIDENCE_STYLE[s.confidence] ?? ""}`}>
                    {s.confidence}
                    {/* Honesty marker: pretend/fallback identifications say so */}
                    {s.source !== "claude" && (
                      <span className="ml-1 text-zinc-500">({s.source})</span>
                    )}
                  </div>
                </td>
                <td className="max-w-xs px-4 py-2 italic text-zinc-400">“{s.comment}”</td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-zinc-500">
                  {new Date(s.spotted_at + "Z").toLocaleString()}
                </td>
                <td className="px-4 py-2">{s.spoken ? "🔊" : "🔇"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
