# Meme Agent Guide

## Project direction

Meme is an interview-ready personal AI knowledge base focused on long-term memory and
explainable tracing and evaluation. Preserve that product direction unless the owner
explicitly changes it and the corresponding decision record is updated.

## Sources of truth

Use the following order when instructions or documents disagree:

1. The owner's explicit instruction for the current task.
2. Accepted architecture decision records in `docs/decisions/`.
3. The GitHub Issue that defines the current task and its acceptance criteria.
4. `docs/architecture/CURRENT-SYSTEM.md` for verified current behavior and dependencies.
5. `docs/refactor/TARGET-ARCHITECTURE.md` and
   `docs/refactor/FEATURE-DECISIONS.md` for the intended direction and detailed scope.
6. `docs/ROADMAP.md` for progress tracking only.

If a new owner decision supersedes an accepted ADR, update or supersede the ADR in the
same change. Do not silently leave conflicting sources of truth.

## Read only what the task needs

- Always read this file and the current GitHub Issue before implementation.
- For architecture or feature-boundary work, read the relevant ADR plus the current and
  target architecture documents.
- For ordinary implementation, inspect the affected code, nearby tests, and only the
  relevant sections of the documentation.
- Do not load every project document by default.
- Treat source code, migrations, and executable configuration as the final authority for
  current runtime facts; correct stale documentation when discovered.

## GitHub workflow and repository safety

- Repository: `sunraiiin/Meme`; default branch: `main`.
- `origin` is the only push target. `upstream` (`lm041520/Comet`) is read-only reference
  material; never open Meme Issues or PRs there and never push to it.
- When using GitHub CLI, explicitly pass `--repo sunraiiin/Meme` for Issue and PR actions.
- Start work from an Issue, create an `agent/<short-description>` branch, make a focused
  change, validate it, and open or update a Draft PR.
- Do not develop directly on `main`. Keep `main` runnable.
- Stage only files that belong to the current Issue; preserve unrelated user changes.
- Use separate Issues and PRs for independent feature removals or migrations.
- Prefer Squash and merge so each completed Issue becomes one clear commit on `main`.

## Product and implementation guardrails

- Follow `docs/decisions/0001-product-scope.md`; do not duplicate its feature list here.
- Hiding a feature, disabling its navigation, and deleting its backend or data are
  different changes. State which one the Issue authorizes.
- Before removing or moving a feature, check frontend routes and state, API routes,
  services, models and migrations, background tasks, storage dependencies, configuration,
  tests, and documentation.
- Scheduled Agent tasks remain an advanced capability and must not depend on external
  notification delivery to expose their results in the application.
- Preserve per-user authorization and data isolation across every API, job, and query.
- Use Alembic for schema changes. Document data impact and a rollback or recovery path;
  do not perform destructive data removal as an incidental refactor.
- Never commit secrets, local credentials, generated private data, or production dumps.
- Keep the repository private until the upstream licensing and attribution question is
  resolved. Do not add a new license that claims rights over copied upstream code.

## Validation

Run checks proportional to the affected area and record them in the PR:

- Frontend changes: from `web/`, run `npm run lint` and `npm run build`.
- Backend Python changes: from `api/`, run `uv run ruff check .` and the closest relevant
  tests or focused runtime check available for the changed behavior.
- Migration changes: review upgrade and downgrade behavior and validate against a safe
  development database when available.
- Docker or configuration changes: validate the resolved Compose configuration and avoid
  embedding machine-specific paths or credentials.
- Documentation-only changes: run `git diff --check` and verify changed local Markdown
  links.

If a check cannot run because infrastructure or credentials are unavailable, say exactly
what was not verified; do not report it as passed.

## Documentation and Skills

- Keep small, task-specific requirements and acceptance criteria in the GitHub Issue.
- Add an ADR only for a durable, cross-cutting decision that future contributors need to
  understand. Update an existing document instead of creating a competing version.
- Mark replaced decisions or guidance as superseded and link to the replacement.
- Add repository Skills under `.agents/skills/` only when a repeatable workflow or stable
  domain knowledge has emerged from real development work.
- Keep each Skill focused on one job. Put routing and invariant rules in `SKILL.md`, longer
  details in `references/`, and deterministic checks in `scripts/` when useful.
- A Skill must point to maintained code or documents and include a way to detect stale
  guidance; do not create speculative Skills merely to fill out a directory.
