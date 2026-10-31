/**
 * App — two pages under one live connection: the porch dashboard (#/) and
 * the stats page (#/stats, 06-F11). Hash routing: no router dependency, and
 * the FastAPI static mount serves index.html for both.
 *
 * One socket (useEventSocket) powers everything live; REST hooks power
 * everything persisted.
 */

import { useEffect, useState } from "react";
import { EventLog } from "./components/EventLog";
import { LiveFeed } from "./components/LiveFeed";
import { SightingsTable } from "./components/SightingsTable";
import { CostumeChart, StatsCards } from "./components/Stats";
import { StatusHeader } from "./components/StatusHeader";
import { useEventSocket } from "./hooks/useEventSocket";
import { useSightings } from "./hooks/useSightings";
import { StatsPage } from "./pages/StatsPage";

export type Page = "live" | "stats";

function currentPage(): Page {
  return location.hash.startsWith("#/stats") ? "stats" : "live";
}

export default function App() {
  const { connected, log, detections, fps, componentStatus, resets } = useEventSocket();
  const { sightings, stats, error } = useSightings(log, resets);
  const [page, setPage] = useState<Page>(currentPage);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-4">
      <StatusHeader connected={connected} componentStatus={componentStatus} page={page} />

      {page === "stats" ? (
        <StatsPage log={log} resets={resets} />
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
