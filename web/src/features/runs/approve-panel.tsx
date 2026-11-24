"use client";

// Task C-09: approval (docs/design/screens/Admin-Approve.dc.html): totals, "what leaves your bank
// account", countdown, Approve / Cancel. After approve, poll GET /api/runs/{run_id} every 1s while
// state is "approved" or "processing" and show it flip to "paid" (~5s, D8). "failed" -> Retry.
import type { Schemas } from "@/lib/api/client";

export function ApprovePanel({ run }: { run: Schemas["RunDetail"] }) {
  return <p className="text-note">Approval panel for run {run.id} (task C-09).</p>;
}
