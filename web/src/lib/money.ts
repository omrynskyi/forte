/**
 * Money on the frontend (NFR-1): the API sends integer cents and we never turn them into floats.
 * Display with formatCents(); read user input with parseDollarsToCents().
 */

export function formatCents(cents: number): string {
  if (!Number.isSafeInteger(cents)) throw new Error(`cents must be an integer, got ${cents}`);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100);
  const rest = abs % 100;
  return `${sign}$${dollars.toLocaleString("en-US")}.${String(rest).padStart(2, "0")}`;
}

/** "1,234.5" | "$1234.50" | "12" -> cents. Returns null if it isn't a valid amount. */
export function parseDollarsToCents(input: string): number | null {
  const s = input.trim().replace(/[$,\s]/g, "");
  const m = /^(\d+)(?:\.(\d{0,2}))?$/.exec(s);
  if (!m) return null;
  const cents = Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

/** 480 -> "8.0", 390 -> "6.5", 75 -> "1.25" (hours are integer minutes in the API). */
export function formatHours(minutes: number): string {
  const whole = Math.trunc(minutes / 60);
  let hundredths = Math.round(((minutes % 60) * 100) / 60);
  let w = whole;
  if (hundredths === 100) {
    w += 1;
    hundredths = 0;
  }
  return hundredths % 10 === 0 ? `${w}.${hundredths / 10}` : `${w}.${String(hundredths).padStart(2, "0")}`;
}

/** "7.5" | "7:30" -> 450 minutes. Quarter-hour precision is plenty. Null if invalid. */
export function parseHoursToMinutes(input: string): number | null {
  const s = input.trim();
  const hm = /^(\d{1,2}):([0-5]\d)$/.exec(s);
  if (hm) return Number(hm[1]) * 60 + Number(hm[2]);
  const dec = /^(\d{1,2})(?:\.(\d{1,2}))?$/.exec(s);
  if (!dec) return null;
  const minutes = Number(dec[1]) * 60 + Math.round((Number(`0.${dec[2] ?? "0"}`) * 60));
  return minutes <= 1440 ? minutes : null;
}
