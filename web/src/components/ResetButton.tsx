/**
 * ResetButton — deletes every sighting and snapshot (06-F12), after an
 * explicit second click in a confirm dialog. Every open dashboard clears
 * itself when the server announces the reset over the event socket.
 */

import { useState } from "react";
import { api } from "../api/client";

export function ResetButton() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = async () => {
    setBusy(true);
    try {
      await api.reset();
      setOpen(false);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-red-700 hover:text-red-300"
      >
        Reset data…
      </button>
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reset-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onKeyDown={(e) => e.key === "Escape" && !busy && setOpen(false)}
        >
          <div className="w-full max-w-sm rounded-xl border border-zinc-700 bg-zinc-900 p-5">
            <h2 id="reset-title" className="text-base font-semibold text-zinc-100">
              Delete all sightings?
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              This deletes every sighting, snapshot and count, and starts the stats over. It
              can't be undone.
            </p>
            {error && <p className="mt-2 text-sm text-red-300">Reset failed: {error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                autoFocus
                disabled={busy}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void reset()}
                className="rounded-md bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-60"
              >
                {busy ? "Deleting…" : "Delete everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
