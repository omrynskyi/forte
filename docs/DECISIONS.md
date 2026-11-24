# Decisions

Settled on Nov 24, 2026. These override `docs/PRD.md` wherever they disagree. Agents: don't
re-decide these. If one blocks you, comment on your issue and stop. To change one, a human edits
this file in its own PR.

| # | Decision | Why | Overrides |
|---|---|---|---|
| D1 | Demo **Dec 3, 2026**. Feature freeze **end of day Dec 1**. Dec 2 is rehearsal only, no features. | Started from zero on Nov 24; ~6 build days incl. Thanksgiving. | Milestones |
| D2 | Code is written by autonomous agents; humans write/triage issues, review PRs, run the demo. Work queue = GitHub Issues + Project board, one issue per PR. | Parallel work without a shared TASKS.md to conflict on. | — |
| D3 | **Cut from the MVP:** passkeys, weekly/semimonthly/monthly schedules, direct deposit hold (ONB-3), overtime/double time, clock-in/out, NOTE-1 change emails, RUN-7 reminders, PAY-4 YTD totals, REP-2 CSV (stretch), multi-company users, PTO payout, YTD wage import, paper checks, "record a payment made outside Forte". | Only what the demo script exercises. | FR table, open questions |
| D4 | **Runs locally** with Docker Compose for the demo. The PRD documents a production deployment path (see ARCHITECTURE.md#deployment). | No hosting risk on stage. | Architecture |
| D5 | Every external dependency is an **adapter with a mock**, picked by env var: `TaxProvider`, `PaymentsProvider`, `BankVerifier`, `EmailSender` (Mailpit), `StorageAdapter` (MinIO/S3). | Swap in real vendors by config; tests stay fast. | Architecture, risks |
| D6 | **Mock tax** = simplified, deterministic rates in basis points, half-up per line. Employee: SS 6.2%, Medicare 1.45%, CA SDI 1.3%, federal 12/10/11% (single/MFJ/HoH, +2% multiple jobs) after W-4 dependents, CA PIT 4/3/3.5% minus $5 per allowance; plus extra withholding. Employer: SS 6.2%, Medicare 1.45%, FUTA 0.6%, CA SUI 3.4%, ETT 0.1%. No wage bases. Labeled "illustrative" in the UI footer. | A real engine is a non-goal; numbers must be exact and repeatable. | RUN-2 ("taxes only via TaxProvider"), accuracy metric ("matches the provider to the cent") |
| D7 | **7 run states**: draft, submitted, approved, processing, paid, failed, cancelled (Calculated merged into Draft; items recalculate on demand). Table in `api/app/payroll/states.py`. | Fewer states, same behavior. | Lifecycle |
| D8 | **Approve sends the payout immediately**: approved → processing → (mock calls signed `/api/webhooks/payments` after 5 s) → paid/failed. The webhook is the only code that sets paid/failed. Retry reuses the run's idempotency key. | Real-provider shape, demo-speed timing. | Journey 3 step 7 |
| D9 | **No fake clock.** `app/clock.py` is the only time source (tests patch it). Seed sets the live period's cutoff to now + 3 h. | Countdown is real on stage. | — |
| D10 | **Auth = magic link only** (15 min, single use) + a dev-only "sign in as" switcher (`/dev`, disabled in prod). Server-side sessions, HttpOnly cookie, same-origin via the Next.js `/api` proxy. | Passkeys are a week of WebAuthn work. | AUTH-1, passwordless feature |
| D11 | **Corrections: reason "missed hours" only, always off-cycle** (no "add to next paycheck"). | Matches the demo script. | Correction flow |
| D12 | *(superseded by D16)* PDF via print stylesheet. | | |
| D13 | **Fernet field encryption** for SSN, EIN, bank account numbers; `*_last4` stored for display. Full values only via the audited reveal endpoint. | NFR-5/6 with minimal code. | — |
| D14 | **Hours** are typed per day (decimal or h:mm), stored as integer minutes. Timesheet states: open → approved / rejected → locked (no employee "submit" step). | Simplest flow that satisfies TIME-1..3. | Design's clock-in, overtime |
| D15 | **Final paycheck proration** (salaried): period salary × workdays worked ÷ workdays in period, half-up. Hourly: approved/open unpaid minutes up to the last day. | Common convention, integer-friendly. | — |
| D16 | **Object storage for paystub PDFs only** (no user uploads; W-4/DE 4 stay form fields). MinIO locally (bucket `forte-paystubs`, **versioning on**: payroll records are kept 4 years), AWS S3 in prod, `MemoryStorage` in tests/CI. PDF rendered **once** with ReportLab right after the run reaches PAID, stored, and **never regenerated** (DB trigger makes the key set-once). Download = authz check, then a **60-second presigned URL signed for `FORTE_S3_PUBLIC_ENDPOINT`** (never `minio:9000`); fallback streams through the API. | A paystub is a legal record; enterprise-grade storage is a course talking point. | D12, PAY-3, data model "PDF location" |
| D17 | Admins invite Admins and Payroll Managers. **Payroll Managers invite Employees only**, by creating the employee record. | Resolves PRD open question. | Open questions |
| D18 | **CA final-pay due date is display only**: involuntary → last day; voluntary with ≥72 h notice → last day; voluntary without notice → last day + 72 h. | We can't move money that fast in a sandbox anyway. | Journey 5 |
| D19 | **No overpayment recovery.** Corrections only pay more. | Resolves open question; matches D11. | Open questions |
| D20 | **Separation of duties:** the approver must not be the member who submitted the run. An Admin may approve a run that includes their own pay. | One Admin in the demo company. | — |
| D21 | Former employees keep read-only access **indefinitely**. | Resolves open question. | Open questions |
| D22 | **One company per user** (membership.user_id is unique). The demo still shows multi-tenancy by signing up a second company live. | Simpler auth. | Data model |
| D23 | **Biweekly only.** Period for pay date P: end = P − 5 days, start = end − 13. Cutoff = P minus `cutoff_lead_days` (1–3, default 2) business days at 17:00 America/Los_Angeles. 6 future periods are kept generated. | Matches the design (pay Fri Nov 13 for Oct 26–Nov 8, approve by Wed 5 PM). | CO-3 |
| D24 | A paystub's id in the API is its **payroll_item_id**. Previews come straight from items of submitted/approved/processing/failed runs; draft/cancelled runs show nothing. | One URL for preview and final. | — |
| D25 | **Web data fetching is client-side** through the typed `$api` client (TanStack Query + openapi-fetch, generated from `api/openapi.json`). | Agents get compile errors instead of runtime drift. | — |
| D26 | **Seed data = the design's company**: Larkspur Bakery, Inc. (see DEMO.md#seed-data). | Screens and demo match. | — |
| D27 | **Mock bank verification:** invalid ABA checksum → failed; account ending `0000` → failed; else verified. Demo routing number `110000000`. | Lets the demo show a failure on purpose. | — |
| D28 | **Countdown states** (RUN-6): more than 24 h → neutral tile; 24 h or less → "Approve today" emphasis; 2 h or less → alert color; past cutoff and unapproved → "At risk of a late paycheck" (alert). The only non-gray token is `--alert`. | Design is grayscale; one accent keeps urgency readable. | — |
| D29 | Host ports: MinIO **9100** (API) / **9101** (console), overridable in `.env`. | Avoids clashing with other local MinIO installs on 9000. | — |
| D30 | Official `minio/minio` images are no longer published; we pin the community fork `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` (includes `mc`). Production uses AWS S3, so this only affects local dev. | Reproducible local stack. | — |
