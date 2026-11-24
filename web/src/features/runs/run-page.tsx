"use client";

// Task C-08: run preview + submit (docs/design/screens/Mgr-Run.dc.html).
// Read the id with useParams<{ runId: string }>(). Fetch GET /api/runs/{run_id} and render buttons
// from `allowed_actions` only (never hard-code who can do what). Render <ApprovePanel run={run} />
// when the caller is an Admin and run.state !== "draft".
import { TaskPlaceholder } from "@/components/ui";

export function RunPage() {
  return <TaskPlaceholder task="C-08" title="Payroll run" design="Mgr-Run" />;
}
