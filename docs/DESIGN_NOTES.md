# Design notes

The designs are HTML mockups in `docs/design/screens/*.dc.html` (open them in a browser, or read
the markup: text, layout and copy are all there). Tokens: `docs/design/tokens.json`. They were
drawn before the scope cut, so **some things on screen are out of scope**. Build the screen, skip
the parts listed under "Ignore".

| Screen | Route | Task | Ignore (cut, see DECISIONS) |
|---|---|---|---|
| Main (sign in) | `/login` | D-01 | "Use a passkey" button and its hint |
| Emp-SignIn (check your email) | `/login` (after submit), `/auth/verify` | D-01 | — |
| Admin-Setup | `/setup`, `/admin/setup` | C-02 | EDD account number, UI rate field, weekly/semimonthly/monthly options (show biweekly only), step 5 "Pay already made this year" |
| Admin-Home | `/admin` | C-03 | — |
| Admin-Approve | `/payroll/runs/[runId]` (Admin view) | C-09 | "record a payment made outside Forté"; "Compared with" diff rows if no previous run |
| Admin-Team | `/admin/team` | C-04 (P1) | — |
| Admin-History | `/admin/history` | C-11 | — |
| Mgr-Employees | `/employees` | C-05 | — |
| Mgr-Employee | `/employees/[employeeId]` | C-06 | Overtime status row, personal email, "unused vacation to pay out", "record final pay as paid outside Forté", direct-deposit hold text |
| Mgr-Timesheets | `/timesheets` | C-07 | overtime columns |
| Mgr-Run | `/payroll`, `/payroll/runs/[runId]` | C-08 | "record a payment made outside Forté", direct-deposit hold notice |
| Mgr-Correction | `/corrections/new?item=<itemId>` | C-10 | "With the next paycheck" option (always off-cycle) |
| Emp-Onboard-1 | `/me/onboarding/address` | D-03 | personal email field (add date of birth instead) |
| Emp-Onboard-2 | `/me/onboarding/taxes` | D-03 | — (add: W-4 dependents amount, multiple jobs, CA allowances) |
| Emp-Onboard-3 | `/me/onboarding/deposit` | D-03 | "I'd rather have a paper check"; change-hold sentence |
| Emp-Home | `/me` | D-02 | "Clock in" button and "You're not clocked in" |
| Emp-Hours | `/me/hours` | D-04 | start/end times, overtime line (enter hours per day instead) |
| Emp-Paystubs | `/me/paystubs` | D-05 | — |
| Emp-Paystub | `/me/paystubs/[itemId]` | D-05, D-06 | — |
| Emp-Deposit | `/me/account` | D-03 | hold period |
| Emp-Former | `/me/former` | D-07 | W-2 line (say "W-2s are not available in this demo") |

Copy style (from the designs): short, plain sentences; say what happens and why ("An approved run
locks. Nobody can edit it, not even you."). Every money figure uses tabular numbers.
