/**
 * Shared chart components (06-F11): the card frame with its table-view
 * toggle, the legend, the tooltip, and the table view itself.
 */

import { useState, type ReactNode } from "react";

export function ChartCard({
  title,
  subtitle,
  table,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  /** The same data as a table: the accessible twin of the chart. */
  table?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    // min-w-0: a grid item may otherwise grow to its content and never shrink back.
    <section className={`min-w-0 rounded-xl border border-zinc-800 bg-zinc-900 p-4 ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
          {subtitle && <p className="text-xs text-zinc-500">{subtitle}</p>}
        </div>
        {table && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            className="shrink-0 rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            aria-pressed={showTable}
          >
            {showTable ? "Show chart" : "Show table"}
          </button>
        )}
      </div>
      {showTable ? <div className="max-h-80 overflow-auto">{table}</div> : children}
    </section>
  );
}

export function Legend({
  items,
  mark = "rect",
}: {
  items: { label: string; color: string }[];
  mark?: "rect" | "line";
}) {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-300">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className={mark === "line" ? "inline-block h-0.5 w-3.5 rounded" : "inline-block h-2.5 w-2.5 rounded-sm"}
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/** Values lead, labels follow; rows keyed with a short line in the series colour. */
export function Tooltip({ x, y, title, rows, width }: {
  x: number;
  y: number;
  title: string;
  rows: TooltipRow[];
  width: number;
}) {
  const boxWidth = 168;
  const left = Math.min(Math.max(x + 12, 0), Math.max(width - boxWidth, 0));
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 rounded-lg border border-white/10 bg-zinc-950/95 px-3 py-2 text-xs shadow-lg"
      style={{ left, top: Math.max(y - 8, 0), width: boxWidth }}
    >
      <div className="mb-1 text-zinc-400">{title}</div>
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-2">
          {row.color && <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: row.color }} />}
          <span className="font-semibold tabular-nums text-zinc-100">{row.value}</span>
          <span className="text-zinc-400">{row.label}</span>
        </div>
      ))}
    </div>
  );
}

export function DataTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-left text-xs">
      <thead>
        <tr className="border-b border-zinc-800 text-zinc-500">
          {head.map((h, i) => (
            <th key={h} className={`py-1.5 pr-3 font-medium ${i > 0 ? "text-right" : ""}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r} className="border-b border-zinc-800/60 text-zinc-300">
            {row.map((cell, i) => (
              <td key={i} className={`py-1 pr-3 ${i > 0 ? "text-right tabular-nums" : ""}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
