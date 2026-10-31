/**
 * Visitors over time (06-F11): one 2px line per category, a crosshair that
 * snaps to the nearest time bucket, and one tooltip listing every series.
 * Arrow keys move the crosshair too, so the readout isn't mouse-only.
 */

import { useState } from "react";
import type { TimelineBucket, VisitorCategory } from "../../api/types";
import { Legend, Tooltip } from "./common";
import { CATEGORY, clock, niceTicks, useWidth } from "./scale";

const HEIGHT = 220; // plot
const AXIS = 24; // x-axis label band, inside the container (no nested scroll)
const LEFT = 32;
const RIGHT = 12;
const TOP = 8;

export function LineChart({ buckets, series, bucketMinutes }: {
  buckets: TimelineBucket[];
  series: VisitorCategory[];
  bucketMinutes: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...buckets.flatMap((b) => series.map((s) => b[s])));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const plotWidth = Math.max(width - LEFT - RIGHT, 1);
  const x = (i: number) => LEFT + (buckets.length <= 1 ? plotWidth / 2 : (i / (buckets.length - 1)) * plotWidth);
  const y = (v: number) => TOP + HEIGHT - (v / top) * HEIGHT;
  const labelEvery = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(plotWidth / 70))));

  const pick = (clientX: number, element: Element) => {
    const left = element.getBoundingClientRect().left;
    const i = Math.round(((clientX - left - LEFT) / plotWidth) * (buckets.length - 1));
    setActive(Math.min(Math.max(i, 0), buckets.length - 1));
  };

  const bucket = active === null ? null : buckets[active];
  return (
    <div>
      <Legend items={series.map((s) => CATEGORY[s])} mark="line" />
      <div ref={ref} className="relative w-full min-w-0" style={{ height: TOP + HEIGHT + AXIS }}>
        {width > 0 && (
          <svg
            width={width}
            height={TOP + HEIGHT + AXIS}
            role="img"
            aria-label={`Visitors every ${bucketMinutes} minutes: ${series.map((s) => CATEGORY[s].label).join(", ")}`}
            tabIndex={0}
            className="outline-none focus-visible:ring-1 focus-visible:ring-zinc-500"
            onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
            onPointerLeave={() => setActive(null)}
            onBlur={() => setActive(null)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                e.preventDefault();
                const step = e.key === "ArrowRight" ? 1 : -1;
                setActive((i) => Math.min(Math.max((i ?? (step > 0 ? -1 : buckets.length)) + step, 0), buckets.length - 1));
              }
            }}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line x1={LEFT} x2={width - RIGHT} y1={y(t)} y2={y(t)}
                      stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"} strokeWidth={1} />
                <text x={LEFT - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11}
                      fill="var(--chart-muted)" className="tabular-nums">{t}</text>
              </g>
            ))}
            {buckets.map((b, i) =>
              i % labelEvery === 0 ? (
                <text key={b.start} x={x(i)} y={TOP + HEIGHT + 16} fontSize={11}
                      // Edge labels hug the plot instead of being cut off.
                      textAnchor={x(i) - LEFT < 30 ? "start" : width - RIGHT - x(i) < 30 ? "end" : "middle"}
                      fill="var(--chart-muted)">{clock(b.start)}</text>
              ) : null,
            )}
            {series.map((s) => (
              <polyline
                key={s}
                fill="none"
                stroke={CATEGORY[s].color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                points={buckets.map((b, i) => `${x(i)},${y(b[s])}`).join(" ")}
              />
            ))}
            {bucket && active !== null && (
              <g>
                <line x1={x(active)} x2={x(active)} y1={TOP} y2={TOP + HEIGHT}
                      stroke="var(--chart-ink-2)" strokeWidth={1} />
                {series.map((s) => (
                  <circle key={s} cx={x(active)} cy={y(bucket[s])} r={4} fill={CATEGORY[s].color}
                          stroke="var(--chart-surface)" strokeWidth={2} />
                ))}
              </g>
            )}
          </svg>
        )}
        {bucket && active !== null && (
          <Tooltip
            x={x(active)}
            y={TOP}
            width={width}
            title={`${clock(bucket.start)} – ${clock(new Date(new Date(bucket.start).getTime() + bucketMinutes * 60_000).toISOString())}`}
            rows={series.map((s) => ({ label: CATEGORY[s].label, value: String(bucket[s]), color: CATEGORY[s].color }))}
          />
        )}
      </div>
    </div>
  );
}
