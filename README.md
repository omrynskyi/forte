# Forté

Payroll that owners and employees can understand. California W-2 payroll MVP for CMPE 272
(Fall 2026): Oleg Mrynskyi, Isaac Kim, Liliya Panfilova, Jagath Jijo. **Sandbox only: all data is
fake and no real money moves.**

## Run it

Needs Docker, [uv](https://docs.astral.sh/uv/), and Node 24.

```bash
make setup     # .env, Python + Node deps, Postgres/Mailpit/MinIO, migrations
make api       # http://localhost:8000/docs
make web       # http://localhost:3000
make seed scene=demo   # demo data (Larkspur Bakery)
```

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Mailpit (magic-link emails) | http://localhost:8025 |
| MinIO console (paystub PDFs) | http://localhost:9101 (user `forte`, password `forte-dev-secret`) |

## Docs

- [PRD](docs/PRD.md): what and why
- [Decisions](docs/DECISIONS.md): what we settled, which overrides the PRD
- [Architecture](docs/ARCHITECTURE.md): system, state machine, conventions, deployment plan
- [Demo plan](docs/DEMO.md): script, seed data, recovery
- [Design notes](docs/DESIGN_NOTES.md): screen → route → task
- [Roadmap](docs/ROADMAP.md): every task by track, dependencies, critical path ([board](https://github.com/users/omrynskyi/projects/3))
- [CLAUDE.md](CLAUDE.md): how we (and our coding agents) work in this repo

## Working on a task

Work is tracked as GitHub Issues, one PR each, grouped into four tracks (A payroll engine, B
platform, C staff web, D employee web + demo) and daily milestones. Pick an unassigned issue whose
dependencies are closed, assign yourself, and follow [CLAUDE.md](CLAUDE.md).
