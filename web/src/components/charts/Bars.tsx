/**
 * Bar forms for the stats page (06-F11):
 *  - SegmentedBar: one whole split into parts (the visitor mix), 28px tall,
 *    a 2px surface gap between parts, shares printed only where they fit.
 *  - RankedBars: horizontal bars for named categories (costumes), one colour,
 *    value at the tip.
 *  - Columns: vertical bars for an ordered count (group sizes), value on the cap.
 * Bars are <=24px thick with a 4px rounded data end, square at the baseline.
 */

import { useState } from "react";
import { Legend, Tooltip } from "./common";
import { niceTicks, useWidth } from "./scale";

export interface Part {
  key: string;
  label: string;
  color: string;
  value: number;
}

export function SegmentedBar({ parts }: { parts: Part[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ part: Part; x: number } | null>(null);
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  const visible = parts.filter((p) => p.value > 0);
  const gap = 2;
  const usable = Math.max(width - gap * Math.max(visible.length - 1, 0), 0);
  let cursor = 0;
  return (
    <div>
      <Legend items={parts.map(({ label, color }) => ({ label, color }))} />
      <div ref={ref} className="relative h-7" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")} role="img">
        {total === 0 && <div className="h-7 rounded bg-zinc-800" />}
        {width > 0 &&
          visible.map((part) => {
            const w = (part.value / total) * usable;
            const left = cursor;
            cursor += w + gap;
            const share = `${Math.round((part.value / total) * 100)}%`;
            // Labels only where they fit with padding: ~7px a character + 16px.
            const fits = w >= share.length * 7 + 16;
            return (
              <div
                key={part.key}
                tabIndex={0}
                className="absolute top-0 h-7 rounded outline-none hover:brightness-110 focus-visible:ring-1 focus-visible:ring-zinc-300"
                style={{ left, width: w, background: part.color }}
                onPointerEnter={() => setHover({ part, x: left })}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover({ part, x: left })}
                onBlur={() => setHover(null)}
                aria-label={`${part.label}: ${part.value} (${share})`}
              >
                {fits && (
                  <span className={`absolute left-2 top-1/2 -translate-y-1/2 text-xs font-semibold ${part.key === "unidentified" ? "text-zinc-950" : "text-white"}`}>
                    {share}
                  </span>
                )}
              </div>
            );
          })}
        {hover && (
          <Tooltip
            x={hover.x}
            y={32}
            width={width}
            title={hover.part.label}
            rows={[{ label: `of ${total}`, value: `${hover.part.value} (${Math.round((hover.part.value / total) * 100)}%)` }]}
          />
        )}
      </div>
    </div>
  );
}

export function RankedBars({ items, color, unit }: {
  items: { label: string; value: number }[];
  color: string;
  unit: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div>
      {items.length === 0 && <p className="text-sm text-zinc-500">Nothing yet.</p>}
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li
            key={item.label}
            className="group flex items-center gap-2 rounded text-xs hover:bg-zinc-800/60"
            title={`${item.label}: ${item.value} ${unit}`}
          >
            <span className="w-[38%] max-w-40 shrink-0 truncate text-zinc-300">{item.label}</span>
            <span className="flex h-5 min-w-0 flex-1 items-center">
              <span
                className="block h-4 rounded-r group-hover:brightness-110"
                style={{ width: `${Math.max((item.value / max) * 100, 1)}%`, background: color }}
              />
            </span>
            <span className="w-7 shrink-0 text-right tabular-nums text-zinc-300">{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const COL_HEIGHT = 140;
const COL_AXIS = 22;

export function Columns({ items, color, unit }: {
  items: { label: string; value: number }[];
  color: string;
  unit: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const ticks = niceTicks(Math.max(1, ...items.map((i) => i.value)));
  const top = ticks[ticks.length - 1];
  const left = 28;
  const band = Math.max((width - left) / Math.max(items.length, 1), 1);
  const barWidth = Math.min(24, band * 0.6);
  const y = (v: number) => 16 + COL_HEIGHT - (v / top) * COL_HEIGHT;
  return (
    <div ref={ref} className="relative w-full min-w-0" style={{ height: 16 + COL_HEIGHT + COL_AXIS }}>
      {width > 0 && (
        <svg width={width} height={16 + COL_HEIGHT + COL_AXIS} role="img"
             aria-label={items.map((i) => `${i.label}: ${i.value}`).join(", ")}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={width} y1={y(t)} y2={y(t)}
                    stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"} strokeWidth={1} />
              <text x={left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11}
                    fill="var(--chart-muted)">{t}</text>
            </g>
          ))}
          {items.map((item, i) => {
            const cx = left + band * i + band / 2;
            const h = y(0) - y(item.value);
            const r = Math.min(4, h / 2, barWidth / 2);
            const x0 = cx - barWidth / 2;
            const yTop = y(item.value);
            // Rounded top corners only: square at the baseline.
            const path = h <= 0 ? "" :
              `M${x0},${y(0)} V${yTop + r} Q${x0},${yTop} ${x0 + r},${yTop} H${x0 + barWidth - r} ` +
              `Q${x0 + barWidth},${yTop} ${x0 + barWidth},${yTop + r} V${y(0)} Z`;
            return (
              <g key={item.label}
                 onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                <rect x={cx - band / 2} y={16} width={band} height={COL_HEIGHT} fill="transparent" />
                {path && <path d={path} fill={color} opacity={hover === i ? 0.85 : 1} />}
                {item.value > 0 && (
                  <text x={cx} y={yTop - 5} textAnchor="middle" fontSize={11} fill="var(--chart-ink-2)">
                    {item.value}
                  </text>
                )}
                <text x={cx} y={16 + COL_HEIGHT + 15} textAnchor="middle" fontSize={11}
                      fill="var(--chart-muted)">{item.label}</text>
              </g>
            );
          })}
        </svg>
      )}
      {hover !== null && (
        <Tooltip x={left + band * hover} y={16} width={width} title={items[hover].label}
                 rows={[{ label: unit, value: String(items[hover].value) }]} />
      )}
    </div>
  );
}
