# Progress log

## Current status
Bootstrap phase started. Repo skeleton, project docs and a MySQL bootstrap configuration have been created in line with the master prompt. The project is now ready for Phase 1 implementation work.

## Build plan (Phases 1–9)

### Phase 1 — Backend foundation
- Create Django backend monorepo structure with `config`, `accounts`, `scheduling`, `notifications`, and `dashboard` apps.
- Add environment-driven settings, MySQL configuration, custom user model and domain models.
- Add migrations, constraints, healthz endpoint and model tests.
- Verify using `python manage.py migrate`, `pytest`, `ruff` and `mypy`.

### Phase 2 — Slot engine & concurrency
- Build `generate_slots` and `book_slot` service layer with lock-first transaction discipline.
- Validate exact overlap logic, slot filtering, cancellation reopening and deadlock retry behaviour.
- Add concurrency regression tests and a `concurrency_demo` management command.

### Phase 3 — REST API, auth and notifications
- Implement DRF endpoints for public and authenticated flows, JWT auth and role-based permissions.
- Add throttling, validation, OpenAPI schema generation and email notifications.
- Seed demo data and verify with API tests and curl smoke checks.

### Phase 4 — Frontend foundation & design system
- Scaffold Next.js app, install UI stack and shadcn elements.
- Build design tokens, reusable primitives, a kitchen-sink page and typed API client.
- Add auth BFF route handlers and cookie policy.

### Phase 5 — Customer booking experience
- Implement `/book`, `/book/confirmation` and `/booking/manage` experiences.
- Handle slot refresh, validation, booking flow states and cancellation UX.
- Run responsive and accessibility review plus Playwright validation.

### Phase 6 — Business dashboard
- Implement the protected dashboard shell, KPI cards, booking calendar and drawer.
- Add filterable datatable, staff management, working-hours editing and command palette.
- Verify role scoping on UI and API.

### Phase 7 — Motion, polish and QA
- Run visual and accessibility audit, fix layout and spacing issues.
- Tune animations, reduce motion support and Lighthouse metrics.
- Record before/after design review and performance results.

### Phase 8 — E2E, CI/CD, Docker and docs
- Add Playwright E2E covering happy path, race conditions and admin/staff flows.
- Add production Dockerfiles, CI workflows and screenshot generation.
- Finalise README, architecture notes and demo script.

### Phase 9 — Adversarial audit and release
- Run a full red-team review across spec, security, concurrency and client robustness.
- Fix release blockers, add regression tests and produce `CHANGELOG.md` and version tag.

## Bootstrap checklist
- [x] Repo skeleton created
- [x] Docs initialized from project prompt
- [x] `.env.example` created
- [x] `docker-compose.yml` created with MySQL 8.4
- [x] `Makefile` scaffolding created
- [ ] MySQL container health is verified with `docker compose up -d mysql && docker compose ps`
- [x] Phase 1 backend project implementation started

## Backend foundation verification (2026-10-08)
- Verified Django settings inheritance by loading `config.settings.test` successfully and confirming `INSTALLED_APPS` includes the default Django app set.
- Confirmed the custom user model, scheduling models, and migration logic are coherent with the project’s model contract.
- Verified backend health using the following commands:
  - `python -m ruff check .`
  - `python -m mypy . --config-file mypy.ini`
  - `python -m pytest -q`
- Result: all checks passed, with `5 passed` in the test suite and no lint or type-check errors reported.

## Phase 2 — Slot engine verification (2026-10-08)
- Implemented the slot-generation and booking service layer in `scheduling/services.py`.
- Added executable tests covering working-hour rules, overlap rejection, duplicate-slot denial, and cancellation reopening in `scheduling/tests/test_slot_engine.py`.
- Verified with the following commands:
  - `python -m pytest scheduling/tests/test_slot_engine.py -q`
  - `python -m ruff check . --fix`
  - `python -m mypy . --config-file mypy.ini`
  - `python -m pytest -q`
- Result: the slot engine passes its dedicated tests and the full backend suite remains green (`8 passed`).

## Phase 3 — Public API and booking flow verification (2026-10-08)
- Implemented the public DRF endpoints and JWT auth flow in `dashboard/views.py`, `dashboard/urls.py`, and `dashboard/serializers.py`.
- Added the booking creation, lookup, and cancellation flow to validate against the product contract for public no-auth booking interactions.
- Fixed a slot-engine parsing bug where DRF serializes `time` objects as `HH:MM:SS`, while the generator and validator were only accepting `HH:MM`.
- Verified with the following commands:
  - `python -m pytest dashboard/tests/test_api.py -q`
  - `python -m pytest -q`
  - `python -m ruff check .`
  - `python -m mypy .`
- Result: the API contract and the full backend regression suite are green (`11 passed`), with lint and type checks passing.

## Local template server verification (2026-10-08)
- Confirmed Django discovers `dashboard/templates/dashboard/home.html` through the app template loader with `APP_DIRS=True`.
- Verified the template routes with `python -m pytest dashboard/tests/test_templates.py -q` (`2 passed`) and `python manage.py check --settings=config.settings.test` (no issues).
- Started the local server from `backend` using `python manage.py runserver 127.0.0.1:8000 --settings=config.settings.test --noreload`; `/` and `/book/` both returned HTTP 200.
- The default settings use MySQL; use the test settings for local SQLite testing unless the MySQL credentials in `.env` are configured. The previously reported template exception was not reproducible after this clean start.

## CR-01 roadmap

### M0 — Impact analysis and spec merge
- [x] Create branch `feature/cr01-multi-org`.
- [x] Add the authoritative CR-01 contract, update Copilot instructions/spec summaries, record deviations, and create impact/button-audit baselines.
- Risk: the workspace began with no commits and all existing project files untracked. Preserve that baseline; do not stage application code as part of the M0 documentation commit.
- Verification: review documentation diff and `git diff --check`; confirm no product-code paths changed.

### M1 — Tenancy data model and Org Code
- [x] Add Organisation and EmailToken models, user role/verification/organisation fields, tenant FKs, migration/backfill, tenant queryset/mixins, permissions, admin registrations and tenant-aware factories.
- [x] Preserve historical booking snapshots and the Staff-first lock; backfill Staff names before detaching old staff logins; remove cancellation-token storage/routes.
- [x] Scope existing catalogue, staff, slot and booking endpoints to verified clients and their organisation; add router-introspection and tenant-isolation regressions.
- [x] Verify empty and populated prior-release migrations on SQLite; 43 backend tests pass and all new Org Code/token/tenant helper modules have 100% coverage.
- [ ] Verify both migration paths on MySQL 8/InnoDB; Docker Engine was unavailable in this environment.
- Verification run: `python -m pytest -q --cov=accounts.services.org_code --cov=accounts.services.email_tokens --cov=accounts.tenancy --cov=scheduling.tenancy --cov-report=term-missing` (43 passed; each selected module 100%); `python -m ruff check .` (clean); `python -m mypy .` (clean); `python manage.py makemigrations --check --dry-run --settings=config.settings.test` (no changes); `python manage.py check --settings=config.settings.test` (no issues).
- Risk: production MySQL DDL/index behavior remains unverified until a MySQL 8/InnoDB service is available. The owner relation is nullable at the database layer only to bootstrap the circular owner/organisation pair; M2 registration must set it before transaction commit.

### M2 — Accounts and verification
- Add Org Code lookup, registration for both portals, verification/resend, portal-aware login, profile/org/password endpoints, emails and stale-unverified purge command; regenerate OpenAPI/types.
- Risk: token single-use/expiry, account enumeration and atomic registration/email delivery behavior.
- Verification: auth matrix, throttling/non-enumeration/token tests; manual owner/client email-verification walkthrough; backend tests, Ruff, mypy and schema validation.

### M3 — Tenant booking engine and API
- Scope the slot engine and API to the tenant; add day states, next-available messages, client bookings/cancellation, admin booking management and tenant-aware demo seed.
- Risk: tenant isolation and preserving lock-first concurrency semantics/privacy while changing booking identity.
- Verification: tenant-isolation matrix, client privacy tests, query-count checks, 10-way race repeated 20 times, multi-tenant race, concurrency demo, tests/lint/types/OpenAPI.

### M4 — Frontend foundation and account screens
- Establish the currently absent Next.js frontend; implement route/layout/nav, generated API client, auth screens, profiles, role guards, welcome/onboarding shell and updated design tokens.
- Risk: frontend project does not exist in this checkout yet; backend contract and cookie/BFF behavior must be stable first.
- Verification: lint, typecheck, Vitest, production build, account journey, axe and responsive screenshots at 390/768/1440.

### M5 — Client booking experience
- Implement gated, profile-bound booking, slot states, availability copy/recovery, confirmation and My Bookings/cancellation.
- Risk: exposing other clients' information or presenting stale availability as bookable.
- Verification: copy/state tests, booking/cancel E2E, tenant privacy E2E, axe, responsive screenshots and Lighthouse targets.

### M6 — Organisation admin dashboard
- Implement tenant-scoped dashboard, calendar, booking drawer/actions, on-behalf booking, client list, staff/services/hours and organisation profile.
- Risk: cross-tenant data leakage, status transition abuse and dense calendar accessibility.
- Verification: admin E2E (including reopen/cancel, complete/no-show and on-behalf booking), tenant isolation, keyboard/axe and responsive screenshots.

### M7 — Simplification and polish
- Complete the after-column of the button audit; simplify copy/layout and validate status colors, accessibility, motion and performance.
- Risk: polish changes regress route behavior or visual/status semantics.
- Verification: complete audit, design review with before/after screenshots, axe, keyboard journeys and Lighthouse gates.

### M8 — E2E, seed, docs and release readiness
- Add file-email E2E helpers, two-organisation demo seed, CI gates, screenshots, setup/demo/architecture docs and backlog updates.
- Risk: non-reproducible local setup and flaky email/race E2E behavior.
- Verification: clean `make up`, full backend/frontend/E2E suites, 10 repeated race runs, all required screenshots and fresh-clone demo.

### M9 — Adversarial audit
- Trace every CR-01 requirement to code/tests; attack tenancy, auth, email tokens, booking concurrency, privacy and data lifecycle; fix release blockers.
- Risk: hidden tenant leaks through filters, nested routes, errors, logs or derived data.
- Verification: attack matrix/fuzz tests, full test/lint/type/build/CI run, fresh-clone walkthrough and audit report. Release only with no open blocker.
