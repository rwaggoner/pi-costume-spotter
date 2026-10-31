/**
 * The REST client: thin, typed fetch wrappers over the edge API.
 *
 * URLs are relative on purpose — in dev, Vite proxies them to the edge app
 * (vite.config.ts); in production the same FastAPI process serves both this
 * bundle and the API, so relative URLs are simply correct.
 */

import type { Health, NightStats, SightingsPage, Stats } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  sightings: (limit = 50, offset = 0) =>
    getJson<SightingsPage>(`/api/sightings?limit=${limit}&offset=${offset}`),
  stats: () => getJson<Stats>("/api/stats"),
  health: () => getJson<Health>("/api/health"),
  /** hours = 0 means every sighting kept. */
  nightStats: (hours: number) => getJson<NightStats>(`/api/stats/night?hours=${hours}`),
  /** Deletes every sighting and snapshot (06-F12). */
  reset: async () => {
    const response = await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: "reset" }),
    });
    if (!response.ok) throw new Error(`/api/reset -> HTTP ${response.status}`);
    return (await response.json()) as { sightings_removed: number; snapshots_removed: number };
  },
  /** URL (not a fetch) — used directly in <img src>. */
  snapshotUrl: (sightingId: string) => `/api/sightings/${sightingId}/snapshot`,
};
