# Roadmap

Board: https://github.com/users/omrynskyi/projects/3 · Demo **Dec 3** · Freeze **end of Dec 1** (D1).

## How to pick work

1. Pick a track (A, B, C, D). One human per track runs agents on that track's queue, in order.
2. Take the first issue in your track whose **Depends on** issues are all closed. Assign yourself.
3. Follow `CLAUDE.md`. One issue, one branch, one PR.
4. Blocked? Help the track that's blocking you, or take a ready issue from another track.

## Critical path

`A-01 → A-03 → A-04 → A-05 → A-13 → B-10 → D-09`  (payroll engine to the paid paystub PDF to the seeded demo)

and `W-01 → C-01 → C-08 → C-09` (the approval screen). Keep these moving first.

## Ready on day 1 (no dependencies)

#1 A-01, #2 A-02, #6 A-06, #15 B-01, #17 B-03, #20 B-06, #21 B-07, #9 B-08, #22 B-09, #25 W-01, #46 D-10

## By track

### A · Payroll engine + paystubs (API)

| Issue | Task | Pri | Size | Depends on | Due |
|---|---|---|---|---|---|
| #1 | **A-01** Mock TaxProvider | P0 | S | — | Day 1-2 |
| #2 | **A-02** Run state machine: transition() | P0 | M | — | Day 1-2 |
| #3 | **A-03** Run builder: regular run items, blockers, totals | P0 | M | #1 A-01 | Day 1-2 |
| #4 | **A-04** Runs API: create, preview, submit, return, cancel, approve | P0 | M | #2 A-02, #3 A-03 | Day 1-2 |
| #5 | **A-05** Mock payments + signed webhook: approved → processing → paid | P0 | M | #2 A-02, #4 A-04 | Day 3-4 |
| #6 | **A-06** Paystubs API, plain-language templates, employee home | P0 | M | — | Day 1-2 |
| #7 | **A-07** Corrections: missed-hours off-cycle run | P0 | M | #3 A-03, #4 A-04 | Day 3-4 |
| #8 | **A-08** Termination + final paycheck run | P0 | M | #3 A-03, #5 A-05 | Day 5-6 |
| #10 | **A-09** Admin dashboard API (countdown data) | P0 | S | #4 A-04, #9 B-08 | Day 5-6 |
| #13 | **A-10** Payroll invariants + end-to-end acceptance tests | P0 | M | #5 A-05, #7 A-07, #8 A-08, #12 A-13 | Day 7 |
| #14 | **A-11** Bonus off-cycle runs | P1 | S | #4 A-04 | Day 7 |
| #11 | **A-12** Paystub PDF rendering (ReportLab) | P0 | S | #6 A-06 | Day 3-4 |
| #12 | **A-13** Paystub PDF storage at PAID + presigned download (MinIO/S3) | P0 | M | #11 A-12, #5 A-05 | Day 5-6 |

### B · Platform: auth, company, people, time, seed (API)

| Issue | Task | Pri | Size | Depends on | Due |
|---|---|---|---|---|---|
| #15 | **B-01** Magic-link auth, sessions, email (Mailpit) | P0 | M | — | Day 1-2 |
| #16 | **B-02** Session cookie → Actor (real auth on every endpoint) | P0 | S | #15 B-01 | Day 1-2 |
| #17 | **B-03** Company setup API: company, funding account, pay schedule + periods | P0 | M | — | Day 1-2 |
| #18 | **B-04** Team: invite Admins/PMs, change roles, remove (last-Admin rule) | P0 | S | #15 B-01 | Day 3-4 |
| #19 | **B-05** Employees + compensation history + audited reveal | P0 | M | #15 B-01 | Day 3-4 |
| #20 | **B-06** Employee self-service: personal info, W-4/DE 4, direct deposit | P0 | M | — | Day 1-2 |
| #21 | **B-07** Timesheets API: log hours, approve/reject, lock | P0 | M | — | Day 1-2 |
| #9 | **B-08** Audit log API + plain-language summaries | P0 | S | — | Day 1-2 |
| #22 | **B-09** Seed: demo scene (Larkspur Bakery, people, periods, hours) | P0 | M | — | Day 1-2 |
| #23 | **B-10** Seed: paid history + demo_paid recovery checkpoint | P0 | S | #22 B-09, #5 A-05, #12 A-13 | Day 5-6 |
| #24 | **B-11** Security sweep: permission matrix + cross-tenant + secret leakage tests | P0 | M | #16 B-02, #18 B-04, #19 B-05, #20 B-06, #21 B-07, #4 A-04, #6 A-06, #7 A-07, #8 A-08, #12 A-13 | Day 7 |

### C · Staff web (Admin + Payroll Manager)

| Issue | Task | Pri | Size | Depends on | Due |
|---|---|---|---|---|---|
| #25 | **W-01** UI kit: forms, table, feedback, dialog, run tracker, countdown | P0 | M | — | Day 1-2 |
| #26 | **C-01** Staff shell: role-based nav, guard, sign out | P0 | S | #25 W-01 | Day 1-2 |
| #27 | **C-02** Company setup wizard (Journey 1) | P0 | M | #25 W-01, #17 B-03 | Day 3-4 |
| #28 | **C-03** Admin home: deadline countdown + run status | P0 | M | #26 C-01, #10 A-09 | Day 5-6 |
| #29 | **C-04** Team and roles page | P1 | S | #26 C-01, #18 B-04 | Day 7 |
| #30 | **C-05** Employees list + add employee | P0 | M | #26 C-01, #19 B-05 | Day 3-4 |
| #31 | **C-06** Employee record: pay history, reveal, end employment | P0 | M | #30 C-05, #8 A-08 | Day 5-6 |
| #32 | **C-07** Timesheets review | P0 | M | #26 C-01, #21 B-07 | Day 3-4 |
| #33 | **C-08** Payroll runs: list, create, preview, submit | P0 | L | #26 C-01, #4 A-04 | Day 3-4 |
| #34 | **C-09** Approve panel + live processing → paid | P0 | M | #33 C-08, #5 A-05 | Day 5-6 |
| #35 | **C-10** Corrections: fix a mistake from a paid paystub | P0 | M | #33 C-08, #7 A-07 | Day 5-6 |
| #36 | **C-11** History and audit log | P0 | M | #26 C-01, #9 B-08, #4 A-04 | Day 5-6 |

### D · Employee web (phone) + demo

| Issue | Task | Pri | Size | Depends on | Due |
|---|---|---|---|---|---|
| #37 | **D-01** Sign in: magic link, verify, dev switcher, routing | P0 | M | #25 W-01, #15 B-01 | Day 1-2 |
| #38 | **D-02** Employee shell (phone) + home | P0 | M | #25 W-01, #6 A-06 | Day 3-4 |
| #39 | **D-03** Onboarding (3 steps) + account page | P0 | M | #38 D-02, #20 B-06 | Day 3-4 |
| #40 | **D-04** Log hours (phone) | P0 | M | #38 D-02, #21 B-07 | Day 3-4 |
| #41 | **D-05** Paystubs list + plain-language paystub | P0 | M | #38 D-02, #6 A-06 | Day 3-4 |
| #42 | **D-06** Download paystub PDF button | P0 | S | #41 D-05, #12 A-13 | Day 5-6 |
| #43 | **D-07** Former employee view | P0 | S | #41 D-05, #8 A-08 | Day 5-6 |
| #44 | **D-08** Mobile + accessibility pass | P1 | M | #39 D-03, #40 D-04, #41 D-05, #43 D-07 | Day 7 |
| #45 | **D-09** Demo runbook, preflight script, two full rehearsals | P0 | M | #13 A-10, #23 B-10, #24 B-11, #28 C-03, #31 C-06, #34 C-09, #35 C-10, #36 C-11, #37 D-01, #39 D-03, #40 D-04, #42 D-06, #43 D-07 | Rehearsal (Dec 2) |
| #46 | **D-10** Presentation slides: problem, product, architecture, deployment | P0 | M | — | Day 5-6 |

## Milestones

- **Day 1-2 · Foundations (Nov 25-26)** (due 2026-11-26): Foundations: payroll core, auth, setup APIs, UI kit, shells. Everything else builds on these. #1 A-01, #2 A-02, #3 A-03, #4 A-04, #6 A-06, #15 B-01, #16 B-02, #17 B-03, #20 B-06, #21 B-07, #9 B-08, #22 B-09, #25 W-01, #26 C-01, #37 D-01
- **Day 3-4 · Core flows (Nov 27-28)** (due 2026-11-28): Core flows end to end: onboarding, hours, run preview, approve, paid. #5 A-05, #7 A-07, #11 A-12, #18 B-04, #19 B-05, #27 C-02, #30 C-05, #32 C-07, #33 C-08, #38 D-02, #39 D-03, #40 D-04, #41 D-05
- **Day 5-6 · Demo complete (Nov 29-30)** (due 2026-11-30): Every demo act works: corrections, termination, PDFs, history, countdown. #8 A-08, #10 A-09, #12 A-13, #23 B-10, #28 C-03, #31 C-06, #34 C-09, #35 C-10, #36 C-11, #42 D-06, #43 D-07, #46 D-10
- **Day 7 · Harden + freeze (Dec 1)** (due 2026-12-01): Feature freeze at end of day. Security sweep, invariants, polish. #13 A-10, #14 A-11, #24 B-11, #29 C-04, #44 D-08
- **Rehearsal (Dec 2)** (due 2026-12-02): Rehearse the demo twice. No new features. #45 D-09
