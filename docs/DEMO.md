# Demo plan (Dec 3, 2026)

Owner: track D (task D-09). Target: about 12 minutes, live, no manual database fixes.

## Setup (on the demo laptop, 30 minutes before)

```bash
make up && make migrate
make seed scene=demo          # resets everything; cutoff = now + 3h
make api                      # terminal 1
make web                      # terminal 2
open http://localhost:8025    # Mailpit (magic links)
```

- Projector: Chrome at 1280 px for staff screens; DevTools device mode (iPhone, 390 px) for
  employee screens. Optional real phone on the same Wi-Fi: set `FORTE_WEB_BASE_URL` and
  `FORTE_S3_PUBLIC_ENDPOINT` to the laptop's LAN IP, `FORTE_DEV_ORIGINS=<that IP>`, restart.
- Sign in as anyone instantly at `/dev` (dev switcher). Use real magic links only in Act 1.

## Acts (each maps to the PRD demo script)

| # | Who | What | Shows |
|---|---|---|---|
| 1 | New Admin | Sign up a **second** company live ("Sunrise Café"): magic link from Mailpit → company details → funding bank (try account ending `0000` to show a failed check, then a good one) → biweekly schedule → setup checklist. | Journey 1, passwordless, multi-tenancy |
| 2 | Rosa (hourly), Sam (salaried) | On the phone view, open invite links, complete the 3 onboarding steps. | Journey 2, mobile, encryption note |
| 3 | Rosa → Ana | Rosa logs hours for 3 days. Ana (PM) approves Rosa's and Tomas's timesheets. | TIME-1/2 |
| 4 | Ana | Create the run for the current period: preview shows totals, company cost, and blockers (if any). Submit for approval. Rosa sees her **preview paystub**. | Journey 3, PAY-2, EMP-5 |
| 5 | Isabel | Admin home: countdown (≈3 h, amber). Approve. Watch **Processing → Paid** in ~5 s. | RUN-6, D8 webhook |
| 6 | Rosa | Open the paystub: plain-language sentence + explained lines. **Download PDF** (served from MinIO via a 60-second presigned link). | PAY-1, PAY-3, D16 |
| 7 | Ana → Isabel | Tomas was short 6.5 hours on the **previous** (already paid) paystub → open a correction → off-cycle run → Isabel approves → Paid. Tomas sees the correction status on his old stub. | Journey 4, COR-1/2 |
| 8 | Ana → Isabel → Jun | Terminate Jun (voluntary with notice) → final paycheck run with CA due date → approve → paid → sign in as Jun: **Former employee** view, download a PDF. | Journey 5, TERM-1/2 |
| 9 | Isabel | History and audit log: every step above, with who and when. Show the MinIO console (`:9101`): versioned objects. | AUD-1, enterprise storage |

**Recovery:** if Act 4–5 breaks, run `make seed scene=demo_paid` (current run already paid) and
continue at Act 6. If the API dies, `docker compose --profile app up` runs the whole stack in
containers.

## Seed data

Company: **Larkspur Bakery, Inc.**, 1180 Alder Street, San Jose, CA 95112, EIN 12-3456789 (fake).
Funding: checking, routing 110000000, account ending 4410. Biweekly, cutoff 2 business days.

| Person | Email | Role | Pay | State in `demo` |
|---|---|---|---|---|
| Isabel Moreno | isabel@larkspur.example | Admin | not on payroll | active |
| Ana Lindqvist | ana@larkspur.example | Payroll Manager | salary $70,720/yr ($2,720.00/period) | onboarded |
| Marisol Vega | marisol@larkspur.example | Employee | salary $72,800/yr | onboarded |
| Priya Raman | priya@larkspur.example | Employee | salary $78,000/yr | onboarded |
| Devon Park | devon@larkspur.example | Employee | hourly $24.50 | onboarded; current hours approved |
| Tomas Weber | tomas@larkspur.example | Employee | hourly $22.00 | onboarded; current hours open; previous stub short 6.5 h |
| Jun Okafor | jun@larkspur.example | Employee | hourly $20.00 | onboarded; current hours approved (terminated in Act 8) |
| Rosa Delgado | rosa@larkspur.example | Employee | hourly $21.00 | invited, not onboarded |
| Sam Whitfield | sam@larkspur.example | Employee | salary $62,400/yr | invited, not onboarded |

Golden number (tests and slides): Devon, 80.0 h × $24.50 = **$1,960.00** gross, single, no extras →
withheld $489.02, take home **$1,470.98** (mock rates, D6).
