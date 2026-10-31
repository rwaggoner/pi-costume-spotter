/**
 * StatsPage — tonight in numbers (06-F11): who came, when, and as what.
 *
 * One window filter above everything (all numbers agree with each other),
 * a hero visitor count with supporting tiles, visitors over time, the
 * costume / no-costume / pet mix, top costumes, and group sizes. Every chart
 * has a table view. While a refetch is in flight the previous render stays,
 * dimmed, instead of flashing a skeleton.
 */

import { useState } from "react";
import type { NightStats, VisitorCategory } from "../api/types";
import { Columns, RankedBars, SegmentedBar } from "../components/charts/Bars";
import { ChartCard, DataTable } from "../components/charts/common";
import { CATEGORY, clock } from "../components/charts/scale";
import { LineChart } from "../components/charts/LineChart";
import type { LogEntry } from "../hooks/useEventSocket";
import { useNightStats } from "../hooks/useNightStats";

const WINDOWS = [
  { hours: 1, label: "Last hour" },
  { hours: 2, label: "Last 2 hours" },
  { hours: 4, label: "Last 4 hours" },
  { hours: 0, label: "Everything" },
];
const MIX: VisitorCategory[] = ["costume", "no_costume", "pet", "unidentified"];
const LINES: VisitorCategory[] = ["costume", "no_costume", "pet"];

function percent(part: number, whole: number) {
  return whole ? `${Math.round((part / whole) * 100)}%` : "—";
}

function Tile({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 truncate text-2xl font-semibold text-zinc-100">{value}</div>
      {note && <div className="mt-0.5 truncate text-xs text-zinc-500">{note}</div>}
    </div>
  );
}

function Tiles({ stats }: { stats: NightStats }) {
  const t = stats.totals;
  const busiest = t.busiest
    ? `${t.busiest.count} visitors in ${stats.window.bucket_minutes} minutes`
    : "No visitors yet";
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-[1.3fr_repeat(4,1fr)]">
      <div className="col-span-2 rounded-xl border border-zinc-800 bg-zinc-900 p-4 md:col-span-1 md:row-span-2">
        <div className="text-xs text-zinc-500">Visitors</div>
        <div className="mt-1 text-5xl font-semibold text-zinc-100">{t.visitors}</div>
        <div className="mt-2 text-xs text-zinc-500">
          {t.people} people, {t.pet} {t.pet === 1 ? "pet" : "pets"}
          {t.first_visit && t.last_visit && (
            <> · {clock(t.first_visit)} to {clock(t.last_visit)}</>
          )}
        </div>
      </div>
      <Tile label="In costume" value={t.costume} note={`${percent(t.costume, t.people)} of people`} />
      <Tile label="No costume" value={t.no_costume} note={`${percent(t.no_costume, t.people)} of people`} />
      <Tile label="Pets" value={t.pet} note={`${t.dogs} dogs, ${t.cats} cats`} />
      <Tile label="Different costumes" value={t.unique_costumes} />
      <Tile label="Groups" value={t.groups} note={`${t.average_group} on average, up to ${t.largest_group}`} />
      <Tile label="Busiest" value={t.busiest ? clock(t.busiest.start) : "—"} note={busiest} />
      <Tile label="Confident IDs" value={percent(stats.confidence.high, t.costume)}
            note={`${stats.confidence.medium} medium, ${stats.confidence.low} low guesses`} />
      <Tile label="Not identified" value={t.unidentified} note="AI unreachable" />
    </div>
  );
}

export function StatsPage({ log, resets }: { log: LogEntry[]; resets: number }) {
  const [hours, setHours] = useState(2);
  const { stats, loading, error } = useNightStats(hours, log, resets);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Time window">
        {WINDOWS.map((w) => (
          <button
            key={w.hours}
            type="button"
            aria-pressed={hours === w.hours}
            onClick={() => setHours(w.hours)}
            className={`rounded-md px-3 py-1 text-sm ${hours === w.hours
              ? "bg-zinc-100 font-semibold text-zinc-900"
              : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"}`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          Couldn't load the stats: {error}
        </p>
      )}
      {!stats && !error && <p className="text-sm text-zinc-500">Loading…</p>}

      {stats && (
        <div className={`space-y-4 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <Tiles stats={stats} />

          <ChartCard
            title="Visitors over time"
            subtitle={`Arrivals every ${stats.window.bucket_minutes} minutes`}
            table={
              <DataTable
                head={["Time", ...LINES.map((s) => CATEGORY[s].label), "Not identified"]}
                rows={stats.timeline.map((b) => [clock(b.start), b.costume, b.no_costume, b.pet, b.unidentified])}
              />
            }
          >
            <LineChart buckets={stats.timeline} series={LINES} bucketMinutes={stats.window.bucket_minutes} />
          </ChartCard>

          <ChartCard
            title="Costume or not"
            subtitle={`All ${stats.totals.visitors} visitors`}
            table={
              <DataTable
                head={["Visitors", "Count", "Share"]}
                rows={MIX.map((c) => [CATEGORY[c].label, stats.totals[c], percent(stats.totals[c], stats.totals.visitors)])}
              />
            }
          >
            <SegmentedBar
              parts={MIX.filter((c) => c !== "unidentified" || stats.totals.unidentified > 0).map((c) => ({
                key: c,
                label: CATEGORY[c].label,
                color: CATEGORY[c].color,
                value: stats.totals[c],
              }))}
            />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard
              className="lg:col-span-2"
              title="Top costumes"
              subtitle={stats.other_costumes
                ? `People and pets; ${stats.other_costumes} more in other costumes`
                : "People and pets"}
            >
              <RankedBars
                items={stats.costumes.map((c) => ({ label: c.costume, value: c.count }))}
                color="var(--series-1)"
                unit="seen"
              />
            </ChartCard>
            <ChartCard
              title="Group sizes"
              subtitle="How many arrived together"
              table={
                <DataTable head={["Group of", "Groups"]} rows={stats.group_sizes.map((g) => [g.size, g.count])} />
              }
            >
              <Columns
                items={stats.group_sizes.map((g) => ({ label: g.size, value: g.count }))}
                color="var(--series-1)"
                unit="groups"
              />
            </ChartCard>
          </div>
        </div>
      )}
    </div>
  );
}
