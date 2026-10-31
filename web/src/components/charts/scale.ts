/**
 * Chart helpers (06-F11): category colours and names, time labels, tick
 * maths, and a width hook so SVG text stays crisp (charts draw at their real
 * pixel width, not a scaled viewBox).
 */

import { useEffect, useRef, useState } from "react";
import type { VisitorCategory } from "../../api/types";

export const CATEGORY: Record<VisitorCategory, { label: string; color: string }> = {
  costume: { label: "In costume", color: "var(--series-1)" },
  no_costume: { label: "No costume", color: "var(--series-2)" },
  pet: { label: "Pets", color: "var(--series-3)" },
  unidentified: { label: "Not identified", color: "var(--series-4)" },
};

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** A clean axis maximum and 3-5 ticks for counts. */
export function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? power * 10;
  const ticks = [];
  for (let t = 0; t <= max + step * 0.001; t += step) ticks.push(Math.round(t));
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + Math.round(step));
  return ticks;
}

