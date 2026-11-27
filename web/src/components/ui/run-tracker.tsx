/**
 * RunStateTracker (W-01): Draft -> Submitted -> Approved -> Paid as pills (D7). `processing` shows
 * under Approved (the money is in flight); `failed` and `cancelled` add a labeled pill after the
 * steps. Pass the API's run state string; labels here are display only.
 */
import { StatusPill } from "./index";

export type RunState = "draft" | "submitted" | "approved" | "processing" | "paid" | "failed" | "cancelled";

const STEPS = ["draft", "submitted", "approved", "paid"] as const;
const LABEL: Record<(typeof STEPS)[number], string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  paid: "Paid",
};

/** Index of the current step, or -1 for failed/cancelled (the labeled pill is current instead). */
export function currentStep(state: RunState): number {
  if (state === "processing") return STEPS.indexOf("approved");
  return STEPS.indexOf(state as (typeof STEPS)[number]);
}

export function RunStateTracker({ state }: { state: RunState }) {
  const cur = currentStep(state);
  const terminal = state === "failed" || state === "cancelled";
  return (
    <ol aria-label="Run progress" className="m-0 flex list-none flex-wrap items-start gap-2 p-0">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-col items-start gap-1">
          <StatusPill current={i === cur}>{LABEL[s]}</StatusPill>
          {s === "approved" && state === "processing" && <span className="text-note">Processing payment</span>}
        </li>
      ))}
      {terminal && (
        <li>
          <span
            aria-current="step"
            className="inline-flex h-8 items-center whitespace-nowrap rounded-full border-2 border-alert px-4 text-sm font-semibold text-alert"
          >
            {state === "failed" ? "Payment failed" : "Cancelled"}
          </span>
        </li>
      )}
    </ol>
  );
}
