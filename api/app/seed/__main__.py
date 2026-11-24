"""Demo data.   uv run python -m app.seed <scene>      (or: make seed scene=<scene>)

Every scene WIPES the database (and the in-bucket paystub PDFs it created), then builds from
scratch. Output is deterministic except for dates, which are computed relative to today so the
demo works on any day. The people and numbers are in docs/DEMO.md#seed-data.

  empty      schema only.
  demo       (B-09) Larkspur Bakery: Admin Isabel Moreno, PM Ana Lindqvist, funding account,
             biweekly schedule, 5 onboarded employees + 2 invited-not-onboarded (Rosa, Sam).
             Current period: pay date = the first Friday >= today + 3 days; cutoff_at = now + 3h
             (so the countdown is live on stage). Hours logged for Devon (approved), Tomas (open),
             Jun (approved). (B-10 adds:) the PREVIOUS period's regular run already PAID, with
             paystubs and stored PDFs, so corrections and history have something to show.
  demo_paid  (B-10) `demo` + the current run created, submitted, approved and PAID. Recovery
             checkpoint: if the live run fails on stage, load this and continue at Act 6.

Build data through the real services (builder, state machine, paid handler, PDF store), not raw
inserts for runs, so seeded runs obey the same rules as live ones. Never call this in prod.
"""

from app.errors import todo

if __name__ == "__main__":
    todo("B-09")
