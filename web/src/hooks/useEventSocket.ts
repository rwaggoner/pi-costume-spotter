/**
 * useEventSocket — the dashboard's live nervous system.
 *
 * Opens ONE WebSocket to /ws/events and derives everything real-time from it
 * (06-F2): the scrolling event log, the current detection boxes for the video
 * overlay, the fps readout, and per-component status lights.
 *
 * Reconnection (06-F10): on close, retry with capped exponential backoff.
 * The `connected` flag is exposed so the UI can say so honestly rather than
 * silently showing a frozen log.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Detection, SystemStatusEvent, WireEvent } from "../api/types";

/** Log entries keep only what the list renders; capped so memory is bounded (06-F7). */
export interface LogEntry {
  id: number;
  timestamp: string;
  kind: string;
  text: string;
}

const LOG_CAP = 200;
// High-frequency plumbing events that would drown the human-readable log.
const SILENT_KINDS = new Set(["FrameProcessed", "SystemStatus"]);

function describe(event: WireEvent): string {
  switch (event.kind) {
    case "NewVisitorSpotted":
      return `Visitor #${event.visitor_id} spotted`;
    case "CostumeIdentified":
      return event.costume
        ? `Identified: ${event.costume} (${event.confidence}) — “${event.comment}”`
        : `No costume — “${event.comment}”`;
    case "SightingLogged":
      return `Sighting saved${event.snapshot_file ? " with snapshot" : ""}`;
    case "CommentSpoken":
      return event.spoken ? `Spoke via ${event.engine}: “${event.text}”` : "Speech failed";
    default:
      return event.kind;
  }
}

export function useEventSocket() {
  const [connected, setConnected] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [fps, setFps] = useState(0);
  const [componentStatus, setComponentStatus] = useState<Record<string, SystemStatusEvent>>({});
  const nextId = useRef(1);

  // Seed component status from REST once: SystemStatus heartbeats are sparse
  // (mostly published at startup or on change), so a dashboard that connects
  // mid-run would otherwise show grey lights until something next happens.
  useEffect(() => {
    api
      .health()
      .then((health) => {
        setComponentStatus((prev) => {
          const seeded = { ...prev };
          for (const [component, s] of Object.entries(health.components)) {
            seeded[component] ??= {
              kind: "SystemStatus",
              timestamp: s.updated_at,
              component,
              ok: s.ok,
              detail: s.detail,
            };
          }
          return seeded;
        });
      })
      .catch(() => {}); // the red "link" light already tells this story
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryDelay = 1000;
    let closedByUnmount = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/events`);

      socket.onopen = () => {
        setConnected(true);
        retryDelay = 1000; // healthy again — reset the backoff
      };

      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as WireEvent;
        if (event.kind === "FrameProcessed") {
          // Not logged, but it drives the overlay + fps display.
          setDetections(event.detections);
          setFps(event.fps);
        } else if (event.kind === "SystemStatus") {
          setComponentStatus((prev) => ({ ...prev, [event.component]: event }));
        }
        if (!SILENT_KINDS.has(event.kind)) {
          setLog((prev) =>
            [
              { id: nextId.current++, timestamp: event.timestamp, kind: event.kind, text: describe(event) },
              ...prev, // newest first (06-F7)
            ].slice(0, LOG_CAP),
          );
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (!closedByUnmount) {
          retryTimer = setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 15_000);
        }
      };
    };

    connect();
    return () => {
      closedByUnmount = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { connected, log, detections, fps, componentStatus };
}
