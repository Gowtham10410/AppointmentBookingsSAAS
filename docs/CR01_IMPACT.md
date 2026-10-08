# CR-01 Impact Analysis

## Baseline and migration strategy

M0 inventory (2026-10-08): this checkout contains a Django backend with public REST/template booking, one accounts/scheduling/dashboard test set, MySQL Compose configuration, and no frontend source, generated OpenAPI file, factories, seed/concurrency command or CI workflow. `.github/workflows/` contains only `.gitkeep`. The M0 worktree began with no commits and existing files untracked; do not stage unrelated scaffold files with a docs-only commit.

The `Staff.name` field is required because Staff becomes a non-login profile and can no longer obtain a name from `Staff.user`; Decision 19 records this compatibility addition. Legacy booking snapshots remain the historical source of customer details. Existing bookings will link to disabled, unverified migration client records, never to a real user based only on matching email.

### Migration paths

**Fresh database:** apply linear migrations from the current initial migrations to the final tenant-aware schema. Create tables/constraints without creating business data; `seed_demo` remains the explicit path for demo organisations. Verify `migrate` on an empty MySQL database and the SQLite test database where supported.

**Existing database:**
1. Create Organisation and EmailToken tables. For populated data, create one clearly named `Demo Organisation` and a disabled, unverified owner placeholder with a reserved non-deliverable address if no suitable admin exists; bind it as owner. Do not make placeholder credentials usable.
2. Add nullable tenant FKs and new profile/booking fields. Preserve existing values while backfilling every Service and Staff to the Demo Organisation. Copy legacy Staff display names from User full name, then email; add required `Staff.name` after the backfill.
3. Map each legacy admin User to `org_admin`; attach all legacy users to the Demo Organisation. For legacy staff users, detach `Staff.user` after the name copy, map the now-disabled legacy identity to the permitted `client` role, and disable login (`is_active=False`, `email_verified_at=NULL`). Exclude these unverified inactive rows from all client-facing and owner client-list queries; preserve the old account row for audit/history rather than deleting it.
4. For each legacy Booking, create or reuse a disabled, unverified migration client in the Demo Organisation, using a collision-safe reserved address derived from the booking id. Preserve `customer_name/email/phone` snapshots exactly, set `client`, `organisation`, and `created_by` to migration-owned records, and do not grant those records login access. If historical booking snapshots share an email, do not merge identities without explicit proof.
5. Remove `cancel_token` only after legacy snapshot/booking backfills and API deployment sequencing are validated. Preserve booking reference semantics and `active_slot` uniqueness exactly.
6. Make tenant and client FKs non-null, add tenant indexes/constraints, and enforce Org Code immutability after initial insert. Keep operations ordered and reversible where practical; document any irreversible data cleanup.

M1 must test both paths: empty schema and a database populated using the pre-CR-01 migrations plus representative users, services, staff, working hours and bookings. The backfill must be idempotent or fail safely, and no migration may issue usable passwords or verification tokens.

## File/module impact

| Existing file/module or planned surface | Required change | Risk | Phase |
|---|---|---:|---|
| `backend/accounts/models.py` | Add Organisation and EmailToken; replace User roles; add full name, phone, organisation and verification fields; case-insensitive email uniqueness | High | M1 |
| `backend/accounts/managers.py` | Normalize email case and retain create_user/create_superuser compatibility with tenant/role requirements | High | M1 |
| `backend/accounts/admin.py` | Register Organisation/EmailToken; update User display, filters and safe token handling | Medium | M1 |
| `backend/accounts/migrations/` | Linear schema and data migrations; fresh/existing paths; backfill owners, clients, staff and tenant FKs | High | M1 |
| `backend/accounts/services/org_code.py` (new) | Prefix/alphabet generation, collision retry, normalizer and immutable-code enforcement | Medium | M1 |
| `backend/accounts/services/email_tokens.py` (new) | Hash, issue, invalidate, consume and expire purpose-scoped tokens | High | M1–M2 |
| `backend/accounts/tenancy.py` (new) | `TenantQuerySet.for_org()`, `TenantScopedMixin`, verified/client/admin permissions and router introspection support | High | M1 |
| `backend/scheduling/models.py` | Add organisation FKs; Staff nullable user/name/phone; Booking client/creator/cancellation metadata; remove cancel token; preserve active-slot uniqueness | High | M1 |
| `backend/scheduling/migrations/` | Backfill Staff names, tenant IDs and legacy booking client identities before non-null constraints | High | M1 |
| `backend/scheduling/tenancy.py` (new) | Shared `assert_same_tenant()` invariant used by slot generation and booking validation | High | M1, M3 |
| `backend/scheduling/services.py` | Derive policy/timezone from organisation; add day result/states; enforce tenant invariant; client-bound booking and authorized cancel while retaining Staff-first lock | Critical | M1, M3 |
| `backend/scheduling/tests/` | Tenant, migration, day-status/state, timezone, privacy, conflict, lock-order and concurrency regression tests | Critical | M1, M3 |
| `backend/dashboard/serializers.py` | Replace public customer-supplied booking fields with client-bound serializers; add tenant-scoped org/client/admin representations | High | M1–M3 |
| `backend/dashboard/views.py` | Require verified client role and tenant-scope existing catalogue/slot/booking lookups; add org lookup, auth/verification/profile/password and admin APIs | Critical | M1–M3 |
| `backend/dashboard/urls.py` and `backend/config/urls.py` | Register CR-01 routes, remove obsolete token lookup/cancellation paths, preserve healthz only for infrastructure | High | M1–M3 |
| `backend/dashboard/tests/test_api.py` | Tenant-scoped catalogue/slot and authenticated booking tests; later wrong-portal, enumeration and full tenant/privacy matrix | Critical | M1–M3 |
| `backend/dashboard/tests/test_templates.py` | Replace legacy no-login templates tests if templates remain; CR-01 product UI moves to Next.js | Medium | M4 |
| `backend/dashboard/templates/dashboard/base.html` | Remove API-health link and old public nav; retire or reduce templates after Next routes exist | Medium | M4 |
| `backend/dashboard/templates/dashboard/home.html` | Remove fake 4.9/5 statistic and clinic copy; replaced by CR-01 salon home in frontend | Medium | M4 |
| `backend/dashboard/templates/dashboard/book.html` | Remove anonymous customer-details form; gated/profile-backed booking moves to frontend | High | M5 |
| `backend/dashboard/templates/dashboard/confirmation.html` | Update confirmation semantics or retire in favor of client booking confirmation route | Medium | M5 |
| `backend/notifications/` | Add verification/reset/welcome/booking/cancellation email services and templates, on-commit delivery/error handling | High | M2–M3 |
| `backend/config/settings/base.py` | Add throttles, email frontend links/default organisation policy, auth settings and any case-insensitive DB support; preserve DB isolation settings | High | M1–M2 |
| `backend/config/settings/dev.py`, `test.py`, `prod.py` | Configure console/file email, test throttles and production cookie/security behavior consistently | Medium | M2, M8 |
| `backend/conftest.py` and app test factories (new/updated) | Tenant-aware user/org/staff/service/booking factories and two-org fixtures | High | M1 onward |
| `backend/**/management/commands/seed_demo.py` (new) | Two labelled demo organisations, owners, staff, services, hours, verified clients and bookings; print demo-only codes/credentials | High | M3, M8 |
| `backend/accounts/management/commands/purge_unverified.py` (new) | Purge expired unverified users and empty owned organisations safely | Medium | M2 |
| `docs/openapi.yaml` (new/generated) | Publish the new CR-01 API contract; remove old public/token API; regenerate frontend types | High | M2–M3 |
| `frontend/` (currently absent) | Scaffold Next.js App Router, strict TypeScript, BFF/cookie auth, generated API types and tests | High | M4 |
| Frontend routes/layouts/middleware (new) | Public, client and owner route groups; role guards use `/auth/me`; middleware checks cookie presence only | High | M4–M6 |
| Frontend navigation/components/tokens (new) | Exact nav order, no health indicator, green booked states, shared controls and simplified button placement | High | M4, M7 |
| Frontend auth/profile hooks and forms (new) | Registration, lookup, verify/resend, portal login, password recovery, profiles and Org Code copy flows | High | M4 |
| Frontend booking hooks/components (new) | Tenant services/staff, slot state, copy catalogue, next-available recovery, confirmation and My Bookings | Critical | M5 |
| Frontend admin dashboard/calendar/components (new) | Tenant-scoped bookings/clients/staff/services/profile, green client-named cards and drawer actions | High | M6 |
| Frontend unit/accessibility tests (new) | Nav order/no-health, form, copy, slot states, copy catalogue, role redirects and axe coverage | High | M4–M7 |
| `frontend/e2e/` (new) | Email-backed owner/client journeys, booking/cancellation race, tenant isolation, wrong portal and accessibility flows | Critical | M8–M9 |
| Factories and migration test fixtures (new) | Prior-release database fixture plus current two-organisation fixture; prove both schema paths | High | M1 |
| `docker-compose.yml` | Add backend/frontend services, file-email mount for E2E, health dependencies and deterministic seed flow | High | M8 |
| `.env.example` | Document Org defaults, file-email/E2E settings and retained secrets without real credentials | Medium | M2, M8 |
| `Makefile` | Replace placeholder targets with install/run/test/lint/typecheck/seed/E2E and reproducible `up` targets | Medium | M8 |
| `.github/workflows/` (currently `.gitkeep` only) | Add backend/frontend/E2E CI, coverage gates, traces and migration/test jobs | High | M8 |
| `README.md` | Replace placeholder setup and single-business description with tenant, verification, owner/client journeys and demo instructions | Medium | M8 |
| `docs/PRODUCT_SPEC.md`, `docs/DESIGN_SYSTEM.md` | Merge CR-01 contract; clearly mark historical/superseded rules and new design semantics | Medium | M0 |
| `docs/DECISIONS.md`, `docs/PROGRESS.md` | Record deviations 8–14, migration rationale and phase gates/results | Low | M0, M8 |
| `docs/ARCHITECTURE.md` | Add tenant model, auth/verification flow, tenant-scoped request flow and updated booking/cancellation sequence | Medium | M3, M8 |
| `docs/BACKLOG.md` | Add only deferred CR-01 ideas (multi-org clients, staff logins, rescheduling, SMS, QR invite, email change) | Low | M8 |
| `docs/CR01_IMPACT.md`, `docs/UI_BUTTON_AUDIT.md` | Maintain phase map and button placement before/after evidence | Low | M0, M7 |
| `docs/DEMO_SCRIPT.md`, `docs/screens/` (new) | Create owner/client walkthrough and verified screenshots after product routes exist | Low | M8 |
| `docs/AUDIT_CR01.md`, `CHANGELOG.md` (new) | Requirement traceability, attack findings/fixes, release notes | High | M9 |

## M0 exclusions
No models, endpoints, templates, frontend code, migrations, dependencies or runtime behavior are changed in M0. The implementation phases own those changes. The existing no-login booking flow and API-health navigation link are documented as baseline behavior to remove in their owning phases.
