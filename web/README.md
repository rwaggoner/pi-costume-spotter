# web/ — the Costume Spotter dashboard

React + TypeScript + Vite + Tailwind. Shows the live camera feed with detection
boxes, a real-time event log, sighting history with snapshots, and costume stats.
Requirements: [docs/requirements/06-dashboard.md](../docs/requirements/06-dashboard.md).

## How it gets its data

| Data | Transport | Code |
|------|-----------|------|
| Live video | MJPEG `<img src="/stream.mjpg">` | [`components/LiveFeed.tsx`](src/components/LiveFeed.tsx) |
| Detection boxes, events, health | one WebSocket `/ws/events` | [`hooks/useEventSocket.ts`](src/hooks/useEventSocket.ts) |
| History & stats | REST `/api/*` | [`api/client.ts`](src/api/client.ts), refreshed event-driven by [`hooks/useSightings.ts`](src/hooks/useSightings.ts) |

All URLs are relative: in dev, Vite proxies them to the edge app
([`vite.config.ts`](vite.config.ts)); in production FastAPI serves this bundle
itself, so the Pi exposes one port.

## Commands

```bash
npm install
npm run dev       # dashboard on :5173, proxying to the edge app on :8000
npm run dev -- --host                     # expose on the LAN
VITE_EDGE_HOST=192.168.1.50:8000 npm run dev   # point at a real Pi
npm run build     # emits dist/ — which the edge app serves when present
npm run lint
```

The TypeScript types in [`src/api/types.ts`](src/api/types.ts) deliberately
mirror the Python API models — if the backend contract changes, start there and
let the compiler point at every affected component.
