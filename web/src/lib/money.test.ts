import assert from "node:assert/strict";
import { test } from "node:test";

import { formatCents, formatHours, parseDollarsToCents, parseHoursToMinutes } from "./money.ts";

test("formatCents", () => {
  assert.equal(formatCents(196000), "$1,960.00");
  assert.equal(formatCents(147098), "$1,470.98");
  assert.equal(formatCents(-2621), "-$26.21");
  assert.equal(formatCents(5), "$0.05");
  assert.throws(() => formatCents(1.5));
});

test("parseDollarsToCents", () => {
  assert.equal(parseDollarsToCents("24.50"), 2450);
  assert.equal(parseDollarsToCents("$78,000"), 7_800_000);
  assert.equal(parseDollarsToCents("0.1"), 10);
  assert.equal(parseDollarsToCents("1.234"), null);
  assert.equal(parseDollarsToCents("abc"), null);
});

test("hours", () => {
  assert.equal(formatHours(480), "8.0");
  assert.equal(formatHours(390), "6.5");
  assert.equal(formatHours(75), "1.25");
  assert.equal(parseHoursToMinutes("7.5"), 450);
  assert.equal(parseHoursToMinutes("7:30"), 450);
  assert.equal(parseHoursToMinutes("25"), null);
});
