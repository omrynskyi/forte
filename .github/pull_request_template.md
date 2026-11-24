Closes #<!-- issue number -->

**Task:** <!-- e.g. A-03 Run builder -->

## What changed
<!-- 2-4 bullets. What a reviewer should look at first. -->

## Checklist
- [ ] Only touched files listed in the issue's "You own" (or explained below why not)
- [ ] Acceptance criteria in the issue are all checked
- [ ] Tests added: happy path, permission/guard failures, cross-tenant 404 (if it takes an id)
- [ ] `make check` passes locally (lint, tests, `make gen` produced no diff)
- [ ] Money is integer cents; no floats (if relevant)
- [ ] Audit entry written in the same transaction for pay / bank / role / run-state changes (if relevant)
- [ ] Added the `needs-human-review` label if this touches money, run state, auth, or audit

## Notes for the reviewer
<!-- Anything surprising, any decision you had to make, anything left for a follow-up issue. -->
