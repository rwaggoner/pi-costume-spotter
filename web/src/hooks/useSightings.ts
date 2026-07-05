/**
 * useSightings — sighting history + stats, refreshed when the live stream
 * says something new was written.
 *
 * Rather than polling on a timer, this listens for the count of
 * SightingLogged entries in the event log and refetches when it grows —
 * event-driven all the way to the UI.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Sighting, Stats } from "../api/types";
import type { LogEntry } from "./useEventSocket";

export function useSightings(log: LogEntry[]) {
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [page, statsBody] = await Promise.all([api.sightings(50), api.stats()]);
      setSightings(page.sightings);
      setStats(statsBody);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // How many "sighting saved" entries the live log currently holds: when this
  // number changes, the DB changed, so refetch. Cheap and precise.
  const loggedCount = useMemo(
    () => log.filter((entry) => entry.kind === "SightingLogged").length,
    [log],
  );

  useEffect(() => {
    void refresh();
  }, [refresh, loggedCount]);

  return { sightings, stats, error, refresh };
}
