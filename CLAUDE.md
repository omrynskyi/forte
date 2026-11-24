# Forte: instructions for coding agents (and humans)

Forte is a California W-2 payroll MVP for CMPE 272 (team: Oleg, Isaac, Liliya, Jagath). **Demo is
Dec 3, 2026. Feature freeze is end of day Dec 1.** Everything external (tax, payments, bank checks,
email) is a mock behind an interface; object storage is MinIO locally and S3 in production.

Read in this order before touching code:
1. Your GitHub issue (`gh issue view <n>`). It lists the files you own and the acceptance criteria.
   `docs/ROADMAP.md` shows every task, its dependencies and the critical path.
2. `docs/DECISIONS.md`: settled decisions. **Do not re-decide them.** If one blocks you, comment on
   the issue and stop; don't work around it.
3. `docs/ARCHITECTURE.md`: how the pieces fit, API and web conventions.
4. The docstring at the top of every file you own. In the skeleton, docstrings ARE the spec.

## Workflow (one issue = one branch = one PR)

```bash
gh issue view 12                       # read the task
git switch -c a-03-run-builder         # <task id>-<slug>, lowercase
# ... work ...
make check                             # lint + tests + regenerated files must be clean
gh pr create --title "A-03: Run builder" --body "Closes #12" [--label needs-human-review]
```

- Only edit files in your issue's **You own** list, plus new files you create. Need to change a file
  someone else owns? Comment on the issue; keep the change minimal and say why in the PR.
- Never push to `main`. Never merge your own PR if it touches money, run state, auth, or audit:
  add the `needs-human-review` label and a human approves.
- Endpoints that aren't built yet return **501 with a task ID** (`{"detail":{"task":"A-04"}}`).
  Seeing one means "that dependency hasn't landed", not "bug".
- Done = acceptance criteria checked, tests added, `make check` green, PR links the issue.

## Non-negotiable rules

1. **Money is integer cents everywhere** (Python `int`, Postgres `BIGINT`, TS `number` that is an
   integer). Never floats, never `Decimal` in JSON, never formatted strings in the API. Use
   `app/money.py` (backend) and `web/src/lib/money.ts` (frontend). Rounding: half-up, once per line.
2. **Hours are integer minutes.**
3. **Tenant isolation:** every query on a company-scoped table filters by `actor.company_id`. Use
   `app/auth/scoping.py` (`get_scoped`, `scoped`). Never take a company_id from the request.
4. **Run state changes only through `app/payroll/state_machine.transition()`.** Allowed transitions
   live in `app/payroll/states.py` and nowhere else. UI buttons come from `allowed_actions`.
5. **Audit in the same transaction:** after any change to pay, bank details, roles, or run state,
   call `app.audit.record(...)`. Never log full SSNs or account numbers.
6. **Services never `commit()`.** `get_db` commits per request. (Exceptions: the mock payments
   provider and the PDF store, which behave like external systems; see their docstrings.)
7. **Taxes only via `TaxProvider`**, payouts only via `PaymentsProvider`, files only via
   `StorageAdapter`. Get them with the FastAPI dependencies in `app/adapters/__init__.py`.
8. **A stored paystub PDF is never regenerated** (D16). Paystubs are never deleted.
9. **Fake data only** (NFR-9). No real names from your contacts, no real SSNs or bank numbers.
10. **Secrets never in the repo.** `.env` is gitignored; add new settings to `.env.example` with a
    dev-safe default and to `app/config.py`.

## Avoiding merge conflicts between agents

- **Schema:** the skeleton owns migration `0001`. If your task truly needs a schema change, add ONE
  new migration (`make migration m="..."`). If another PR merged a migration first, rebase and set
  your `down_revision` to the new head. Never edit a merged migration.
- **Generated files** (`api/openapi.json`, `web/src/lib/api/schema.d.ts`): never hand-edit, never
  hand-merge. On conflict: take either side, then run `make gen`.
- **`api/tests/factories.py`:** append new helpers at the bottom; don't change existing signatures.
- **`app/main.py`, `web/src/app/**/layout.tsx`, `web/src/components/ui`:** already wired. Routers
  are registered; pages exist as placeholders. Replace the placeholder in YOUR page only.
- **Lockfiles** (`uv.lock`, `package-lock.json`): avoid adding dependencies. If you must, say so in
  the PR title (`[deps]`) and regenerate the lockfile on rebase instead of merging it by hand.
- Optional: if the team runs AgentBus (`agentbus` skill), register with `squad=<your track>` and
  claim the files in your issue's **You own** list before writing.

## Commands

```bash
make setup        # first time: .env, deps, containers, migrations
make up           # Postgres :5432, Mailpit :8025, MinIO :9100 (console :9101) + versioned bucket
make api          # FastAPI on :8000 (docs at http://localhost:8000/docs)
make web          # Next.js on :3000 (proxies /api/* to :8000)
make test-api     # pytest (needs Postgres; storage/email are in-memory)
make test-web     # typecheck + lint (+ `cd web && npm test` for unit tests)
make gen          # regenerate openapi.json + web types after changing API schemas
make check        # what CI runs
make seed scene=demo   # load demo data (empty | demo | demo_paid)
```

## Repo map

```
api/app/
  main.py            all routers registered (don't edit)
  config.py          FORTE_* settings          db.py / clock.py / money.py / audit.py / errors.py
  models/            full schema (owned by skeleton)      schemas/   the API contract (Pydantic)
  routers/           one file per area, each = one task   auth/      Actor, role deps, scoping
  adapters/          tax, payments, bank, email, storage interfaces + mock/ implementations
  payroll/           states.py (table), state_machine.py, builder.py
  paystubs/          templates.py, pdf.py, pdf_store.py (created by A-06/A-12/A-13)
  services/          readiness.py, timesheets.py (shared, implemented)
  seed/              demo scenes
api/tests/           conftest (db per test + as_actor), factories.py
web/src/
  app/(public|staff|employee)/   routes; each placeholder names its task + design screen
  components/ui/     primitives       features/   page-sized components     lib/   api client, money, session
docs/                PRD, DECISIONS, ARCHITECTURE, DEMO, DESIGN_NOTES, design/screens/*.dc.html
```
