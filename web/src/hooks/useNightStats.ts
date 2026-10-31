/**
 * useNightStats — the stats page's data (06-F11), refetched when a sighting is
 * saved, when the data is reset, when the window changes, and once a minute
 * (so the timeline's "now" edge keeps moving on a quiet night).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { NightStats } from "../api/types";
import type { LogEntry } from "./useEventSocket";

export function useNightStats(hours: number, log: LogEntry[], resets: number) {
  const [stats, setStats] = useState<NightStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await api.nightStats(hours));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [hours]);

  const loggedCount = useMemo(
    () => log.filter((entry) => entry.kind === "SightingLogged").length,
    [log],
  );

  useEffect(() => {
    void refresh();
  }, [refresh, loggedCount, resets]);

  useEffect(() => {
    const timer = setInterval(() => void refresh(), 60_000);
    return () => clearInterval(timer);
  }, [refresh]);

  return { stats, loading, error };
}
