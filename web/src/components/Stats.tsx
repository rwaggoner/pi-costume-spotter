/**
 * Stats — headline numbers + a dependency-free costume bar chart (06-F9).
 *
 * The chart is plain divs with percentage widths rather than a charting
 * library: at "top ten costumes" scale a library adds 100 KB to save 15 lines.
 */

import type { Stats as StatsData } from "../api/types";

export function StatsCards({ stats }: { stats: StatsData | null }) {
  const cards = [
    { label: "Total sightings", value: stats?.total_sightings ?? "…" },
    { label: "Today", value: stats?.sightings_today ?? "…" },
    { label: "Top costume", value: stats?.top_costumes[0]?.costume ?? "—" },
  ];
  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <div className="text-xs uppercase text-zinc-500">{card.label}</div>
          <div className="mt-1 truncate text-2xl font-semibold text-zinc-100">{card.value}</div>
        </div>
      ))}
    </div>
  );
}

export function CostumeChart({ stats }: { stats: StatsData | null }) {
  const top = stats?.top_costumes ?? [];
  const max = top[0]?.count ?? 1;
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-300">Costumes seen</h2>
      {top.length === 0 && <p className="text-sm text-zinc-500">Nothing identified yet.</p>}
      <ul className="space-y-2">
        {top.map((entry) => (
          <li key={entry.costume} className="text-sm">
            <div className="mb-0.5 flex justify-between text-zinc-400">
              <span>{entry.costume}</span>
              <span>{entry.count}</span>
            </div>
            <div className="h-2 rounded bg-zinc-800">
              <div
                className="h-2 rounded bg-emerald-500"
                style={{ width: `${(entry.count / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
