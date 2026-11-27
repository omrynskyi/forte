import assert from "node:assert/strict";
import { test } from "node:test";

import { clockOffsetMs, countdownState, formatRemaining } from "./countdown-state.ts";

const H = 3_600_000;

test("countdownState boundaries (D28)", () => {
  assert.equal(countdownState(24 * H + 1), "neutral");
  assert.equal(countdownState(24 * H), "today");
  assert.equal(countdownState(2 * H + 1), "today");
  assert.equal(countdownState(2 * H), "urgent");
  assert.equal(countdownState(1), "urgent");
  assert.equal(countdownState(0), "late");
  assert.equal(countdownState(-5 * H), "late");
});

test("clockOffsetMs corrects a skewed local clock", () => {
  const server = "2026-12-01T10:00:00Z";
  const local = Date.parse(server) - 90_000; // local clock 90 s behind
  assert.equal(clockOffsetMs(server, local), 90_000);
});

test("formatRemaining", () => {
  assert.equal(formatRemaining(26 * H + 5 * 60_000), "1d 2h");
  assert.equal(formatRemaining(3 * H + 5 * 60_000), "3h 05m");
  assert.equal(formatRemaining(12 * 60_000 + 9_000), "12m 09s");
  assert.equal(formatRemaining(45_000), "45s");
  assert.equal(formatRemaining(-1000), "0s");
});
