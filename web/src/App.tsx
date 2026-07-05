/**
 * App — the dashboard layout.
 *
 * One socket (useEventSocket) powers everything live; one REST hook
 * (useSightings) powers everything persisted. Layout: feed + live log on top,
 * stats and history below.
 */

import { EventLog } from "./components/EventLog";
import { LiveFeed } from "./components/LiveFeed";
import { SightingsTable } from "./components/SightingsTable";
import { CostumeChart, StatsCards } from "./components/Stats";
import { StatusHeader } from "./components/StatusHeader";
import { useEventSocket } from "./hooks/useEventSocket";
import { useSightings } from "./hooks/useSightings";

export default function App() {
  const { connected, log, detections, fps, componentStatus } = useEventSocket();
  const { sightings, stats, error } = useSightings(log);

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-4">
      <StatusHeader connected={connected} componentStatus={componentStatus} />

      {error && (
        <p className="mb-3 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          API error: {error} — is the edge app running? (docs/setup-dev.md)
        </p>
      )}

      <main className="grid gap-4 lg:grid-cols-3">
        {/* Live feed dominates; the event log rides alongside at equal height. */}
        <section className="lg:col-span-2">
          <LiveFeed detections={detections} fps={fps} connected={connected} />
        </section>
        <section className="min-h-64 lg:max-h-[480px]">
          <EventLog log={log} />
        </section>

        <section className="space-y-4 lg:col-span-2">
          <StatsCards stats={stats} />
          <SightingsTable sightings={sightings} />
        </section>
        <section>
          <CostumeChart stats={stats} />
        </section>
      </main>
    </div>
  );
}
