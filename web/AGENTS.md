<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Forte web conventions

Read the repo root `CLAUDE.md` first (it applies here too), then `docs/ARCHITECTURE.md#web`.
- Data: client components + `$api` from `@/lib/api/client` (typed from the API). No server-side fetching of API data.
- Money: integer cents only. `formatCents()` / `parseDollarsToCents()` from `@/lib/money`.
- UI: primitives from `@/components/ui`, tokens from `globals.css`. Designs are in `docs/design/screens/`.
- `useSearchParams()` must sit inside a `<Suspense>` boundary (Cache Components). Read route params with `useParams()`.
