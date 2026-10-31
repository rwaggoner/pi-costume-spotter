/**
 * Types mirroring the edge API's JSON contracts.
 *
 * Two sources of truth exist on the Python side, and each is mirrored here:
 *  - REST response models  -> edge/costume_spotter/api/routes.py
 *  - WebSocket event shapes -> edge/costume_spotter/events/events.py
 *    (`BaseEvent.as_wire_dict`: dataclass fields, minus image bytes, plus `kind`)
 *
 * If a field changes on the Python side, the compiler makes the break visible
 * everywhere in this app — which is the point of maintaining the mirror.
 */

// ---------- REST ----------

export interface Sighting {
  id: string;
  spotted_at: string; // ISO timestamp
  costume: string | null; // null = person in regular clothes (03-F3)
  confidence: "high" | "medium" | "low" | "unknown";
  comment: string;
  spoken: boolean;
  has_snapshot: boolean;
  detector: string;
  source: "claude" | "pretend" | "fallback";
  box: BoundingBox;
}

export interface SightingsPage {
  sightings: Sighting[];
  limit: number;
  offset: number;
}

export interface Stats {
  total_sightings: number;
  sightings_today: number;
  top_costumes: { costume: string; count: number }[];
  per_hour: { hour: string; count: number }[];
}

/** /api/stats/night — the stats page (06-F11). Times are ISO UTC ("Z"). */
export type VisitorCategory = "costume" | "no_costume" | "pet" | "unidentified";

export interface TimelineBucket extends Record<VisitorCategory, number> {
  start: string;
}

export interface NightStats {
  window: { start: string; end: string; bucket_minutes: number; hours: number | null };
  totals: Record<VisitorCategory, number> & {
    visitors: number;
    people: number;
    dogs: number;
    cats: number;
    groups: number;
    average_group: number;
    largest_group: number;
    unique_costumes: number;
    first_visit: string | null;
    last_visit: string | null;
    busiest: { start: string; count: number } | null;
  };
  timeline: TimelineBucket[];
  costumes: { costume: string; count: number }[];
  other_costumes: number;
  group_sizes: { size: string; count: number }[];
  confidence: { high: number; medium: number; low: number };
}

export interface Health {
  components: Record<string, { ok: boolean; detail: string; updated_at: string }>;
  stream_fps: number;
  bus: { subscriber: string; queued: number; dropped: number }[];
}

// ---------- WebSocket events ----------

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Detection {
  box: BoundingBox;
  confidence: number;
  label: string;
}

/** Every message on /ws/events has a `kind` discriminator. */
export type WireEvent =
  | FrameProcessedEvent
  | NewVisitorSpottedEvent
  | GroupSpottedEvent
  | CostumeIdentifiedEvent
  | GreetingReadyEvent
  | SightingLoggedEvent
  | CommentSpokenEvent
  | SystemStatusEvent
  | DataResetEvent;

interface EventBase {
  kind: string;
  timestamp: string;
}

export interface FrameProcessedEvent extends EventBase {
  kind: "FrameProcessed";
  detections: Detection[];
  fps: number;
}

export interface NewVisitorSpottedEvent extends EventBase {
  kind: "NewVisitorSpotted";
  visitor_id: number;
  box: BoundingBox;
  group_id: string;
  /** person | dog | cat */
  visitor_type: string;
}

/** People who arrived together; snapshots are stripped from the wire. */
export interface GroupSpottedEvent extends EventBase {
  kind: "GroupSpotted";
  group_id: string;
  visitors: { visitor_id: number; box: BoundingBox; visitor_type: string }[];
}

/** The words spoken for a group: greeting, plus shout-outs for small groups. */
export interface GreetingReadyEvent extends EventBase {
  kind: "GreetingReady";
  group_id: string;
  text: string;
  sighting_ids: string[];
}

export interface CostumeIdentifiedEvent extends EventBase {
  kind: "CostumeIdentified";
  sighting_id: string;
  visitor_id: number;
  costume: string | null;
  confidence: string;
  comment: string;
  source: string;
  box: BoundingBox;
  detector: string;
  group_id: string;
  group_size: number;
  visitor_type: string;
}

export interface SightingLoggedEvent extends EventBase {
  kind: "SightingLogged";
  sighting_id: string;
  costume: string | null;
  comment: string;
  snapshot_file: string | null;
}

export interface CommentSpokenEvent extends EventBase {
  kind: "CommentSpoken";
  sighting_id: string;
  text: string;
  engine: string;
  spoken: boolean;
}

export interface SystemStatusEvent extends EventBase {
  kind: "SystemStatus";
  component: string;
  ok: boolean;
  detail: string;
}

/** Everything was deleted from the dashboard's reset button (06-F12). */
export interface DataResetEvent extends EventBase {
  kind: "DataReset";
  sightings_removed: number;
  snapshots_removed: number;
}
