import { RunPage } from "@/features/runs/run-page";

export const metadata = { title: "Payroll run" };

// C-08 owns run-page.tsx (preview, submit, return to draft). C-09 owns approve-panel.tsx, which
// run-page renders for an Admin when the run is submitted or later.
export default function PayrollRunPage() {
  return <RunPage />;
}
