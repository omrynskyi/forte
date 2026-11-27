/**
 * Countdown state function (RUN-6, D28). Pure, so it is unit tested with `node --test`.
 *   more than 24 h left -> "neutral"
 *   24 h or less        -> "today"   ("Approve today")
 *   2 h or less         -> "urgent"  (alert color)
 *   past cutoff         -> "late"    ("At risk of a late paycheck", alert color)
 */
export type CountdownState = "neutral" | "today" | "urgent" | "late";

const HOUR_MS = 3_600_000;

export function countdownState(msLeft: number): CountdownState {
  if (msLeft <= 0) return "late";
  if (msLeft <= 2 * HOUR_MS) return "urgent";
  if (msLeft <= 24 * HOUR_MS) return "today";
  return "neutral";
}

/** Server clock minus local clock, measured once when the page gets `serverTime`. */
export function clockOffsetMs(serverTime: string, localNowMs: number): number {
  return Date.parse(serverTime) - localNowMs;
}

/** "2d 4h", "3h 05m", "12m 09s", "45s". Whole seconds, never negative. */
export function formatRemaining(msLeft: number): string {
  const total = Math.max(0, Math.floor(msLeft / 1000));
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${pad(m)}m`;
  if (m > 0) return `${m}m ${pad(s)}s`;
  return `${s}s`;
}

export const COUNTDOWN_LABEL: Record<CountdownState, string> = {
  neutral: "Time left to approve",
  today: "Approve today",
  urgent: "Approve now",
  late: "At risk of a late paycheck",
};
