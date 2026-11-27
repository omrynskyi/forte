"use client";
/**
 * <Countdown cutoffAt serverTime /> (RUN-6, D28). Pass the API's ISO strings. The clock offset is
 * measured once on mount (server time minus local time), then it ticks every second from the local
 * clock. The visible digits are aria-hidden; a visually hidden `aria-live="polite"` line holds only
 * the state label, so screen readers hear changes of state, not every second.
 * Set `approved` once the run is approved: the "late" warning no longer applies.
 */
import { useEffect, useRef, useState } from "react";

import { cx } from "./ui/cx";
import { clockOffsetMs, COUNTDOWN_LABEL, countdownState, formatRemaining } from "./countdown-state";

export function Countdown({
  cutoffAt,
  serverTime,
  approved,
  className,
}: {
  cutoffAt: string;
  serverTime: string;
  approved?: boolean;
  className?: string;
}) {
  // Prerender-safe: start from the server's clock (no Date.now() during render). After mount the
  // offset (server minus local) is measured once from the first serverTime, then we tick each second.
  const firstServerTime = useRef(serverTime);
  const [now, setNow] = useState(() => Date.parse(serverTime));

  useEffect(() => {
    const offset = clockOffsetMs(firstServerTime.current, Date.now());
    const tick = () => setNow(Date.now() + offset);
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);

  const msLeft = Date.parse(cutoffAt) - now;
  const state = countdownState(msLeft);

  if (approved) {
    return (
      <div className={cx("rounded-md bg-paper-alt p-6", className)}>
        <p className="eyebrow">Cutoff</p>
        <p className="text-heading m-0">Approved before the cutoff</p>
      </div>
    );
  }

  const alert = state === "urgent" || state === "late";
  return (
    <div
      className={cx(
        "flex flex-col gap-1 rounded-md p-6",
        alert ? "border-2 border-alert bg-card" : state === "today" ? "tile-gradient" : "bg-paper-alt",
        className,
      )}
    >
      <p className={cx("eyebrow", state === "today" && "text-on-tile-soft", alert && "text-alert")}>
        {COUNTDOWN_LABEL[state]}
      </p>
      <p aria-hidden className={cx("text-figure m-0", alert && "text-alert")}>
        {state === "late" ? "Past cutoff" : formatRemaining(msLeft)}
      </p>
      <p aria-live="polite" className="sr-only">
        {COUNTDOWN_LABEL[state]}
      </p>
      {/* Time left for assistive tech, read on demand (not live) so it doesn't announce every second. */}
      <p className="sr-only">{state === "late" ? "The cutoff has passed." : `About ${formatRemaining(msLeft)} until the cutoff.`}</p>
    </div>
  );
}
