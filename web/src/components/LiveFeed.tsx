/**
 * LiveFeed — the MJPEG stream with detection boxes drawn on a canvas overlay.
 *
 * The video is a plain <img> pointed at /stream.mjpg (that's all MJPEG needs —
 * ADR-007). Boxes arrive separately over the WebSocket in *source-frame pixel
 * coordinates* (06-F6), so drawing scales them by the ratio between the frame's
 * natural size and the element's rendered size. Keeping boxes out of the video
 * itself is what makes this overlay toggleable.
 */

import { useEffect, useRef, useState } from "react";
import type { Detection } from "../api/types";

interface Props {
  detections: Detection[];
  fps: number;
  connected: boolean;
}

export function LiveFeed({ detections, fps, connected }: Props) {
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [showBoxes, setShowBoxes] = useState(true);

  // Redraw whenever detections change. One rAF per WS message (~15/s) is cheap.
  useEffect(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;

    const frame = requestAnimationFrame(() => {
      // Match the canvas's pixel grid to its on-screen size.
      canvas.width = img.clientWidth;
      canvas.height = img.clientHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!showBoxes || img.naturalWidth === 0) return;

      const scaleX = img.clientWidth / img.naturalWidth;
      const scaleY = img.clientHeight / img.naturalHeight;
      for (const det of detections) {
        const { x, y, width, height } = det.box;
        ctx.strokeStyle = "#34d399"; // emerald — visible on both day and night scenes
        ctx.lineWidth = 2;
        ctx.strokeRect(x * scaleX, y * scaleY, width * scaleX, height * scaleY);
        ctx.fillStyle = "#34d399";
        ctx.font = "12px ui-monospace, monospace";
        ctx.fillText(
          `${det.label} ${(det.confidence * 100).toFixed(0)}%`,
          x * scaleX + 4,
          y * scaleY - 6,
        );
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [detections, showBoxes]);

  return (
    <div className="relative overflow-hidden rounded-xl border border-zinc-800 bg-black">
      <img
        ref={imgRef}
        src="/stream.mjpg"
        alt="Live camera feed"
        className="block w-full"
      />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" />

      <div className="absolute left-2 top-2 flex items-center gap-2 rounded bg-black/60 px-2 py-1 text-xs text-zinc-200">
        <span
          className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-500"}`}
          title={connected ? "live" : "disconnected"}
        />
        <span>{fps.toFixed(0)} fps</span>
      </div>

      <button
        onClick={() => setShowBoxes((v) => !v)}
        className="absolute right-2 top-2 rounded bg-black/60 px-2 py-1 text-xs text-zinc-200 hover:bg-black/80"
      >
        {showBoxes ? "hide boxes" : "show boxes"}
      </button>
    </div>
  );
}
