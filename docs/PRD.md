# Forte Product Requirements

> **Status (Nov 24, 2026):** this PRD is the product intent. Where it disagrees with
> [`DECISIONS.md`](DECISIONS.md) (scope cut, mocks, 7-state lifecycle, object storage, dates), the
> decisions win. Architecture, deployment and the demo plan are in
> [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`DEMO.md`](DEMO.md).

Payroll MVP for CMPE 272 Section 49, Fall 2026 · Oleg Mrynskyi, Isaac Kim, Liliya Panfilova, Jagath Jijo

Nov 4, 2026 · @Oleg Mrynskyi

## Overview and problem

Forte is a payroll app for small businesses that owners and employees can understand without a payroll background. The MVP will be demoed on December 1, 2026, running California W-2 payroll end to end in a sandbox.

Payroll is software a small business can't afford to get wrong, and the incumbents (ADP, Gusto, Paychex, QuickBooks Payroll, Rippling) are better known for their frustrations than their features. Reviews and forums for those tools keep repeating the same complaints, which split cleanly by who is using the product.

| Who | Pain point we keep seeing | How Forte answers it |
| --- | --- | --- |
| Owner | Fixing a payroll mistake is slow and manual | A built-in correction flow with visible status, done through off-cycle runs |
| Owner | Bonuses and off-cycle runs are hard to get right | Off-cycle runs are a first-class run type with a preview before approval |
| Owner | Approval deadlines are easy to miss | A countdown to payroll cutoff on the Admin dashboard |
| Owner | Simple tasks take too many clicks | Short, role-specific flows with one primary action per screen |
| Employee | Logging in is a struggle | Magic links and passkeys, no expiring passwords |
| Employee | Mobile clock-in is buggy | The employee side is designed for the phone first |
| Employee | Paystubs and W-2s disappear after leaving a job | Former employees keep read-only access to their documents |
| Employee | The paystub itself is unreadable | A plain language breakdown of gross to net on every paystub, previewable before payday |

One survey found that 42 percent of workers find the taxes and deductions on their paycheck confusing. That number is the clearest single argument for Forte's focus on explaining pay, not just calculating it.

## Goals, non-goals and scope

The goal is a working, demoable product that shows payroll can be accurate, transparent and a lot less stressful for both the person running it and the person getting paid.

### Goals

- An Admin can set up a company and approve a real-looking payroll in one sitting.
- Every number on a paycheck is correct to the cent and can be traced back to who changed what.
- An employee can open a paystub on their phone and understand where their money went.
- Mistakes get fixed through the product, never by redoing payroll by hand.
- Nobody misses a payday because an approval slipped.

### Non-goals

- Writing our own tax engine. Tax calculation comes from a sandbox tax API.
- Moving real money. All funding and direct deposits are simulated.
- Customer support tooling, help desks or live chat.
- Broader HR features like PTO accrual, benefits enrollment, performance reviews or recruiting.
- Contractors (1099), multi-state employees, or anyone outside California.
- Year-end W-2 generation beyond a stretch goal.

### Scope constraints

Forte supports US W-2 employees who live and work in California only. Tax calculation and money movement run in a payroll or banking provider's sandbox, so no real funds are transferred. All data in the system is fake, including names, SSNs and bank details. The feature list freezes at the October 9 milestone and anything new goes to the stretch list.

## Users and roles

Forte has three active roles plus a read-only state for people who have left. The key rule is separation of duties, since the person who prepares payroll can never be the person who approves it, and nobody can raise their own pay.

**Admin.** Usually the owner. Signs up the company, connects the funding bank account, sets the pay schedule, manages members and roles, and is the only role that can approve or cancel a payroll. A company needs at least one Admin at all times.

**Payroll Manager.** Often an office manager or bookkeeper. Owns employee records, compensation, timesheet approval and preparing runs, including off-cycle runs and terminations. Can't approve payroll and can't edit their own compensation.

**Employee.** Joins through an invite, logs hours if hourly, manages their own address, tax withholding and direct deposit, and views paystubs. Can't change their pay rate or job title.

**Former Employee.** An Employee whose employment has ended. Keeps sign-in and read-only access to their own paystubs and tax documents, and nothing else.

### Permission matrix

| Action | Admin | Payroll Manager | Employee | Former Employee |
| --- | --- | --- | --- | --- |
| Edit company profile, EIN, address | Yes | No | No | No |
| Connect or change funding bank account | Yes | No | No | No |
| Set or change pay schedule | Yes | No | No | No |
| Invite members and assign roles | Yes | Employees only | No | No |
| Create and edit employee records | Yes | Yes | No | No |
| Set compensation (others) | Yes | Yes | No | No |
| Set own compensation | No, another Admin must | No | No | No |
| Approve timesheets | Yes | Yes | No | No |
| Log own hours (hourly) | Yes | Yes | Yes | No |
| Create and preview payroll runs | Yes | Yes | No | No |
| Approve or cancel a payroll run | Yes | No | No | No |
| Start a correction or off-cycle run | Yes | Yes | No | No |
| Terminate an employee | Yes | Yes | No | No |
| Edit own address, withholding, direct deposit | Yes | Yes | Yes | No |
| View full SSN or bank numbers of others | Yes, on demand | Yes, on demand | No | No |
| View own paystubs and documents | Yes | Yes | Yes | Read-only |
| View payroll history and reports | Yes | Yes | No | No |
| View audit log | Yes | Own actions only | No | No |

Admins and Payroll Managers can also be on payroll themselves, in which case they get the Employee abilities for their own record. Revealing a full SSN or account number is a deliberate action that gets written to the audit log.

## Core user journeys

Five journeys make up the demo. If all five work end to end with seeded fake data, the MVP is done.

### 1. Company setup (Admin)

1. Admin enters an email and gets a magic link, then registers a passkey.
2. Admin enters the company's legal name, EIN and California address.
3. Admin connects a funding bank account through the sandbox provider and confirms it.
4. Admin picks a pay schedule (weekly, biweekly, semimonthly or monthly) and the first pay date.
5. Admin invites a Payroll Manager and the first employees, and sees a setup checklist until everything required is done.

### 2. Employee onboarding (Employee)

1. Employee opens the invite link on their phone and signs in without creating a password.
2. Employee confirms legal name and enters SSN, date of birth and home address.
3. Employee fills out federal W-4 and California DE 4 withholding.
4. Employee adds direct deposit details, which are checked against the sandbox provider.
5. Employee lands on a home screen showing their next pay date. Until all four steps are done, they're flagged as not ready and blocked from payroll.

### 3. Regular payroll run (Payroll Manager then Admin)

1. Hourly employees log hours during the pay period from their phone.
2. Payroll Manager approves timesheets, and approved hours lock once the run is submitted.
3. Payroll Manager creates the run, which pulls compensation, approved hours and withholding into a draft.
4. Forte calculates taxes through the sandbox API and shows a preview with totals per employee and company cost.
5. Payroll Manager submits the run for approval. Employees can now preview their upcoming paystub.
6. Admin sees the deadline countdown, reviews the preview and approves. The run locks.
7. On pay date the sandbox processes the run, employees get paid and receive a paystub with the plain language breakdown.

### 4. Fixing a mistake (Payroll Manager then Admin)

1. Someone spots an error on a paid run, like missed hours or a wrong rate.
2. Payroll Manager opens a correction from the original paystub and picks what was wrong.
3. Forte creates an off-cycle correction run that pays (or recovers) only the difference, linked to the original.
4. Admin approves the correction run. The affected employee sees the correction status on their paystub the whole time.

### 5. Termination and former employee access

1. Payroll Manager terminates an employee with an end date and reason.
2. Forte creates an off-cycle final paycheck run, and an Admin approves it. Under California rules the final pay deadline depends on the separation type, so the UI shows the due date.
3. After the final paycheck, the person becomes a Former Employee and keeps read-only access to their paystubs and documents.

## Functional requirements

P0 items must work for the December 1 demo. P1 items are planned but can slip to the stretch list without breaking the demo.

| ID | Area | Requirement | Priority |
| --- | --- | --- | --- |
| AUTH-1 | Auth | Users sign in with an email magic link or a passkey. No passwords. | P0 |
| AUTH-2 | Auth | Magic links expire after 15 minutes and work once. | P0 |
| AUTH-3 | Auth | Every API call is checked against the caller's role and company. | P0 |
| CO-1 | Company | Admin creates a company with legal name, EIN and address, and EIN format is validated. | P0 |
| CO-2 | Company | Admin connects and verifies a funding bank account through the sandbox. | P0 |
| CO-3 | Company | Admin sets a pay schedule and first pay date, and Forte generates upcoming pay periods. | P0 |
| CO-4 | Company | Admin invites members by email and assigns a role. | P0 |
| CO-5 | Company | A company always has at least one Admin, and the last Admin can't be removed. | P0 |
| EMP-1 | Employees | Payroll Manager creates an employee record and sends an invite. | P0 |
| EMP-2 | Employees | Compensation is salary or hourly, stored with an effective date, and history is kept. | P0 |
| EMP-3 | Employees | A Manager or Admin can't edit their own compensation. | P0 |
| EMP-4 | Employees | Employees can't change their own pay rate or job title. | P0 |
| EMP-5 | Employees | Employees missing SSN, address, withholding or direct deposit are blocked from payroll and listed on the run preview. | P0 |
| ONB-1 | Onboarding | Employee completes personal info, W-4, DE 4 and direct deposit from an invite. | P0 |
| ONB-2 | Onboarding | Employee can edit their own address, withholding and direct deposit later. | P0 |
| ONB-3 | Onboarding | Direct deposit changes have a short hold before they apply to a run, and the employee is notified. | P0 |
| TIME-1 | Time | Hourly employees log hours per day for the current pay period from a phone. | P0 |
| TIME-2 | Time | Payroll Manager or Admin approves or rejects timesheets with a note. | P0 |
| TIME-3 | Time | Hours for a pay period lock once its run is submitted. | P0 |
| RUN-1 | Payroll | Payroll Manager creates a regular run for a pay period and previews gross, taxes, deductions and net per employee. | P0 |
| RUN-2 | Payroll | Taxes come from the sandbox tax API, never from our own formulas. | P0 |
| RUN-3 | Payroll | Only an Admin can approve or cancel a run, and only before cutoff. | P0 |
| RUN-4 | Payroll | An approved run is locked and can't be edited. Changes go through a new run. | P0 |
| RUN-5 | Payroll | Off-cycle runs support bonuses, corrections and final paychecks. | P0 |
| RUN-6 | Payroll | The Admin dashboard shows a countdown to the next payroll cutoff. | P0 |
| RUN-7 | Payroll | Admins get reminder notifications as cutoff approaches with a run still unapproved. | P1 |
| PAY-1 | Paystubs | Every paystub has a plain language breakdown of gross to net. | P0 |
| PAY-2 | Paystubs | Employees can preview their upcoming paystub once a run is submitted. | P0 |
| PAY-3 | Paystubs | Employees can download paystubs as PDF. | P0 |
| PAY-4 | Paystubs | Year-to-date totals show on each paystub. | P1 |
| COR-1 | Corrections | A correction is opened from an existing paystub and creates a linked off-cycle run for the difference only. | P0 |
| COR-2 | Corrections | Correction status is visible to the affected employee. | P0 |
| TERM-1 | Termination | Terminating an employee sets an end date and creates a final paycheck run. | P0 |
| TERM-2 | Termination | Former employees keep read-only access to their paystubs and documents. | P0 |
| NOTE-1 | Notifications | Employees are notified by email when their pay rate or bank details change. | P0 |
| NOTE-2 | Notifications | Employees are notified when a paystub is ready. | P1 |
| AUD-1 | Audit | Every change to pay, bank details, roles or run state is logged with who, when, before and after. | P0 |
| AUD-2 | Audit | Audit entries can't be edited or deleted through the app. | P0 |
| REP-1 | Reports | Admin sees payroll history and a per-run summary of totals and company cost. | P0 |
| REP-2 | Reports | Admin exports a run summary as CSV. | P1 |

## Signature features

These six features are what make Forte worth demoing. Each one maps to a specific complaint from the research, and each gets extra design and test time.

### Plain language paystub

Every paystub opens with a short sentence like "You earned $2,400 this period. $612 went to taxes and deductions, and $1,788 landed in your account." Under it, each line item (federal income tax, Social Security, Medicare, CA PIT, CA SDI) has a one-line explanation of what it is and why it was taken. The standard line-by-line paystub stays available underneath for anyone who wants it. Explanations are written by us and stored as templates, not generated on the fly.

### Paystub preview

Once a Payroll Manager submits a run, each employee can see a preview of their upcoming paystub, clearly marked as not final. If the run changes or gets cancelled, the preview updates or disappears. This gives people a few days to catch a mistake before the money moves.

### Deadline countdown

The Admin dashboard shows how long is left before the next payroll cutoff, along with the run's current state. The countdown changes color as cutoff gets close, and a run past cutoff without approval is flagged as at risk of a late paycheck. Cutoff is calculated from the pay date and the sandbox provider's processing lead time.

### Correction flow

Instead of reopening an approved run, a correction starts from the paystub that was wrong. The Payroll Manager picks the reason (missed hours, wrong rate, missed bonus, other), enters the correct values, and Forte builds an off-cycle run for the difference only. The correction carries its own status (opened, in review, approved, paid) and links back to the original so the history reads clearly.

### Former employee access

Leaving a job no longer means losing your paystubs. Former employees sign in the same way as before and see a read-only view of every paystub and tax document from their time at the company. They can't edit anything and see nothing about other employees.

### Passwordless login

Magic links and passkeys replace passwords entirely, so there's nothing to forget or rotate every few weeks. Passkeys are offered right after the first magic link sign-in, and magic links remain as a fallback for new devices.

## Payroll run lifecycle

Every run, regular or off-cycle, moves through the same state machine, and nothing else in the app can change a run's state.

See the state diagram in [ARCHITECTURE.md](ARCHITECTURE.md#payroll-run-lifecycle-d7) (7 states after D7).

A run can be sent back to Draft or cancelled up until approval. Once an Admin approves it, the run and its items never change again. If a payout fails, the run waits in Failed and the retry reuses the same idempotency key, so nobody gets paid twice. A mistake on a paid run is fixed by a new correction run that goes through the whole cycle from Draft.

Hours lock when a run is submitted, so a timesheet edited after that point applies to the next period or to a correction. A run past cutoff without approval stays in Submitted and is flagged on the Admin dashboard.

## Data model

The model is built around one rule, which is that anything touching money is append-only or versioned, never overwritten. Every table carries `company_id` so tenant isolation can be enforced on every query.

| Entity | What it holds | Key relationships | Notes |
| --- | --- | --- | --- |
| Company | Legal name, EIN, address, pay schedule, cutoff lead time | Has many Members, Employees, PayPeriods | EIN encrypted at rest |
| User | Email, passkey credentials | Has many Memberships | One user can belong to more than one company |
| Membership | Role (Admin, Payroll Manager, Employee), status | Links User to Company, optionally to Employee | Former Employee is a status, not a role |
| Employee | Legal name, DOB, address, hire date, end date, onboarding status | Belongs to Company, has Compensations, Withholdings, BankAccounts | SSN encrypted at field level |
| Compensation | Type (salary or hourly), amount in cents, effective date | Belongs to Employee | New row per change, old rows kept |
| Withholding | W-4 and DE 4 fields, effective date | Belongs to Employee | Versioned like Compensation |
| BankAccount | Routing number, account number, hold-until date, status | Belongs to Employee or Company | Account number encrypted at field level |
| PayPeriod | Start, end, pay date, cutoff | Belongs to Company, has one regular PayrollRun | Generated from the pay schedule |
| Timesheet | Daily hours entries, status, approver | Belongs to Employee and PayPeriod | Locked when its run is submitted |
| PayrollRun | Type (regular, bonus, correction, final), state, totals, idempotency key | Belongs to Company and PayPeriod, has PayrollItems, may link to an original run | State changes only through the state machine |
| PayrollItem | Gross, each tax and deduction, net, all in cents | Belongs to PayrollRun and Employee | Immutable once the run is approved |
| Paystub | PDF object key, SHA-256, S3 version id, rendered-at (set once) | Belongs to PayrollItem | PDF rendered once at PAID, stored in S3/MinIO, never regenerated; former employees keep read access |
| Correction | Reason, original paystub, status | Links original PayrollItem to a correction PayrollRun | Status visible to the employee |
| AuditLog | Actor, action, entity, before, after, timestamp, IP | Belongs to Company | Insert-only, no update or delete grants |
| Notification | Recipient, type, sent at | Belongs to User | Email only for the MVP |

All money columns are `BIGINT` cents. Rates for hourly pay are stored as cents per hour, and anything that needs fractional math (like overtime) is computed in integer cents with an explicit rounding rule, then stored as cents.

## Non-functional requirements

The bar is that nobody can be paid twice, paid the wrong amount, or have their SSN leak, even in a sandbox with fake data.

| ID | Area | Requirement |
| --- | --- | --- |
| NFR-1 | Money | All amounts are integer cents end to end, in the database, the API and the frontend. No floats anywhere money is handled. |
| NFR-2 | Money | Totals on a run always equal the sum of its items, checked by a test on every run. |
| NFR-3 | Idempotency | Every call that moves money carries an idempotency key, so a retry can never pay someone twice. |
| NFR-4 | Integrity | Run state changes happen in a single database transaction with a row lock on the run. |
| NFR-5 | Security | SSNs and bank account numbers are encrypted at the field level and masked by default (last 4 only). |
| NFR-6 | Security | Only roles that need sensitive fields can reveal them, and each reveal is logged. |
| NFR-7 | Security | Every query is scoped by company, and cross-tenant access is covered by tests. |
| NFR-8 | Security | Sessions use secure, HTTP-only cookies. Secrets live in environment variables, never in the repo. |
| NFR-9 | Data | Only fake data is used, from the first commit onward. |
| NFR-10 | Audit | Every change to pay, bank details, roles or run state writes an audit entry in the same transaction as the change. |
| NFR-11 | Mobile | Employee screens work well at 375 px wide and are fully usable on a phone. |
| NFR-12 | Accessibility | Core flows meet WCAG 2.1 AA for contrast, labels and keyboard use. |
| NFR-13 | Performance | Previewing a run for 50 employees takes under 5 seconds, sandbox calls included. |
| NFR-14 | Reliability | If the sandbox tax or payments API is down, runs wait in their current state and can be retried safely. |
| NFR-15 | Testability | Every run state and transition has automated tests before any UI is built on top of it. |

## Architecture and tech stack

The frontend never touches money or sensitive fields directly. Every calculation, state change and payment call goes through the FastAPI backend.

See the system diagram in [ARCHITECTURE.md](ARCHITECTURE.md#system).

The tax and payments sandbox sits behind one adapter interface in the backend, with a mocked version that returns the same shapes. That keeps the team unblocked if sandbox access is slow, and it makes the state machine tests fast and repeatable.

| Layer | Choice | Notes |
| --- | --- | --- |
| Frontend | Next.js, TypeScript | Deployed on Vercel free tier |
| Backend | FastAPI (Python) | Deployed on Render or Fly.io free tier |
| Database | PostgreSQL | Managed instance from the API host |
| Tax and payments | Payroll or banking provider sandbox | Provider still to confirm, mocked adapter as fallback |
| Email | Transactional email service | Mailpit locally; Resend/SES in production |
| Object storage | S3 API (MinIO locally, AWS S3 in production) | Paystub PDFs only, versioned bucket, presigned downloads |
| Design | Figma | Wireframes and flows |
| Code and CI | GitHub | Tests run on every pull request |

There are three environments. Local runs against the mocked provider, staging runs against the real sandbox with seeded fake companies, and the demo runs on staging.

### Deployment plan

The demo runs on one laptop with Docker Compose (Postgres, Mailpit, MinIO) and every third-party
service mocked behind an adapter. Production uses the same code with different configuration:
Next.js on Vercel, the FastAPI container on Render/Fly.io/App Runner, managed Postgres, an AWS S3
bucket with versioning and 4-year retention for paystub PDFs, a transactional email provider, and
an embedded-payroll vendor for tax and payouts. GitHub Actions runs the checks on every pull
request and deploys on merge. Full table: [ARCHITECTURE.md#deployment](ARCHITECTURE.md#deployment).

## Success metrics and demo acceptance

Forte succeeds if all five core journeys run live on December 1 with no manual database fixes, and the numbers below hold.

| Metric | Target | How we check it |
| --- | --- | --- |
| Payroll accuracy | Every run in the demo matches the sandbox tax API to the cent | Automated test comparing run totals to the provider response |
| Double payments | Zero, including when a payment call is retried | Test that replays the same idempotency key |
| State machine coverage | 100% of states and transitions tested | Test report in CI |
| Setup time | A new Admin goes from sign-up to first approved run in under 15 minutes | Timed walkthrough with seeded employees |
| Employee onboarding | Under 5 minutes on a phone | Timed walkthrough on a real phone |
| Paystub clarity | 4 of 5 classmates can explain their net pay from the breakdown alone | Quick hallway test before the demo |
| Audit completeness | Every change in the demo script appears in the audit log | Manual check against the demo script |

### Demo script

- [ ] Admin signs up, connects the sandbox bank and sets a biweekly schedule
- [ ] Two employees onboard from their phones, one salaried and one hourly
- [ ] Hourly employee logs hours and the Payroll Manager approves them
- [ ] Payroll Manager prepares a run and employees see their paystub preview
- [ ] Admin approves against the countdown and the run locks
- [ ] Employee opens the plain language paystub
- [ ] A missed-hours mistake is corrected through an off-cycle run
- [ ] One employee is terminated, gets a final paycheck and signs in as a Former Employee
- [ ] Audit log shows every step above

## Milestones and timeline

The project runs from October 5 to the final demo on December 1, 2026, with phases overlapping by about a week so nobody sits idle waiting on another piece.

Superseded: see D1 in [DECISIONS.md](DECISIONS.md) and the milestones on the GitHub Project board.

As of November 4 the team is in the hours and payroll runs phase, with approval and paystubs starting November 9. Each phase ends with its features merged, tested and running on staging, not just built locally. Anything not on staging by November 24 is cut from the demo.

## Risks and mitigations

Tax complexity and scope creep are the two risks most likely to sink the demo, and both are handled by keeping scope narrow rather than by working harder.

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Tax calculation is more complex than expected | High | High | Limit scope to California W-2 employees and use a sandbox tax API instead of writing our own engine |
| Scope creep from extra HR features | High | Medium | Feature list froze at the Oct 9 milestone, and anything new goes to the stretch list |
| Sandbox API access is delayed or restricted | Medium | High | Applied for access in week one, and build against a mocked service with the same interface as a fallback |
| Security mistakes with sensitive employee data | Medium | High | Fake data only, SSNs and bank numbers encrypted from the first commit, access rules reviewed at each milestone |
| Team members have uneven availability | Medium | Medium | Clear owner per feature, a weekly check-in, and tasks small enough to hand off |
| Payroll edge cases break the state machine | Medium | Medium | Tests for every run state and transition before any UI is built on top |
| Thanksgiving week falls between the end of testing (Nov 24) and the demo (Dec 1) | Medium | Medium | Rehearse the demo script on staging by Nov 24 and treat anything unfinished as cut |

## Stretch goals and open questions

Nothing here blocks the demo. Stretch items get picked up only if every P0 is done and tested.

### Stretch list

- Year-end W-2 generation and download for current and former employees
- In-app and SMS notifications in addition to email
- Paid time off balances shown on the paystub
- Simple payroll cost report by month
- Multi-state support, starting with one neighboring state

### Open questions

- [ ] Which sandbox provider do we use for tax calculation and money movement, and does it cover CA SDI and PIT?
- [ ] How long is the direct deposit change hold, 24 hours or one full pay cycle?
- [ ] Should a Payroll Manager be allowed to invite other Payroll Managers, or only employees?
- [ ] Does a correction that recovers an overpayment need its own approval wording for the employee?
- [ ] How long do former employees keep access in the demo story, indefinitely or a fixed number of years?
- [ ] Do we need overtime and double time for hourly employees in the MVP, or can that be a P1?
