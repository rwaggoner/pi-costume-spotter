import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-mode wiring (06-F5): the Vite dev server proxies API traffic to the edge
// app, so the dashboard code always talks to relative URLs ("/api/...") and
// never needs to know whether it's running against localhost or a real Pi.
// To point at a Pi on your LAN: VITE_EDGE_HOST=192.168.1.50:8000 npm run dev
const edgeHost = process.env.VITE_EDGE_HOST ?? "localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": `http://${edgeHost}`,
      "/stream.mjpg": `http://${edgeHost}`,
      "/ws": { target: `ws://${edgeHost}`, ws: true },
    },
  },
  // In production the FastAPI app serves this directory itself (06-F4) —
  // see _WEB_DIST in edge/costume_spotter/api/app.py.
  build: { outDir: "dist" },
});
