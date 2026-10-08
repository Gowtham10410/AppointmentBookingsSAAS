# CR-01 — Multi-Organisation Booking (authoritative)

> This document supersedes conflicting statements in `PRODUCT_SPEC.md`, `DESIGN_SYSTEM.md`, README and earlier decisions. Where it is silent, the older documents still apply.

## 1. Product vision
A booking app for beauty parlours, salons and similar businesses. Each organisation is created by an owner, receives a unique Org Code and shares it with existing customers, who register as clients with verified email. Clients book against their organisation's staff availability. Owners manage bookings, clients, staff, services and hours.

## 2. Personas and journeys
**Organisation owner (`org_admin`)** registers owner and organisation details, verifies email, then logs in to the Organisation portal. First login presents a welcome card with Org Code, copy code/invite link actions, and checklist: Add services → Add staff → Set working hours → Share your Org Code. Daily use includes seeing and managing appointments and clients.

**Client (`client`)** registers with name, email, phone, password and Org Code (or invite link `/register/client?org=CODE`), verifies email, logs in to the Client portal, books with the organisation's services/staff, and sees bookings and profile details. Organisation membership is permanent and singular.

## 3. Scope
**In scope:** multiple organisations; Org Code; client accounts; email verification and password reset; Client and Organisation login portals; client and organisation profiles; owner client list and on-behalf booking; per-organisation booking settings; green booked-slot cards; human-readable unavailable-day explanations; owner onboarding checklist.

**Removed:** public no-login booking; `cancel_token` cancellation; `staff` login role; Staff are profiles managed by the owner, not users; API-health indicators in UI.

**Out of scope:** payments, ML/forecasting, SMS, rescheduling UI, recurring appointments, clients belonging to multiple organisations, staff logins, email change, social login. Record future ideas in `docs/BACKLOG.md`.

## 4. Domain model changes
**Organisation (`accounts.Organisation`):** name (≤120), business type (`salon`, `beauty_parlour`, `spa`, `barbershop`, `clinic`, `other`), unique immutable `org_code`, phone, address, city, state, postal code, country (India default), IANA timezone (Asia/Kolkata default), buffer minutes (0–60, default 10), minimum lead time (0–1440, default 30), booking window (1–180 days, default 30), active flag, created timestamp, and protected OneToOne owner.

**User (`accounts.User`):** globally unique, case-insensitive email login; `full_name`, phone, role (`org_admin` or `client`), required organisation FK, nullable `email_verified_at`. Unverified users cannot log in.

**EmailToken (`accounts.EmailToken`):** user, purpose (`verify_email` or `reset_password`), SHA-256 token hash, expiry, used timestamp and created timestamp. Plaintext is emailed only. Tokens are single-use; issuing a token invalidates earlier unused tokens of that purpose. Verification expires after 24 hours; reset after 1 hour.

**Staff:** add organisation FK; nullable user FK (no staff login); required display `name` (≤100) and optional phone. Keep specialization, active flag and service M2M; empty services means all active services. Backfill `name` from the linked user's full name/email before detaching legacy staff users.

**Service:** add organisation FK. **WorkingHours:** unchanged; tenant derived through Staff.

**Booking:** add organisation FK, required client FK (PROTECT), created-by user FK, cancelled timestamp and nullable cancelled-by FK. Remove `cancel_token`. Keep customer name/email/phone as immutable snapshots from the client profile. Keep `active_slot` and unique `(staff, date, start_time, active_slot)` unchanged.

Invariant: `booking.organisation == staff.organisation == service.organisation == client.organisation`, enforced in the service layer and tested.

## 5. Org Code
Format `PREFIX-XXXXX` (example `GLOW-7K4Q9`). Prefix is the first 3–4 ASCII letters of the organisation name, falling back to `ORG`; suffix uses `ABCDEFGHJKMNPQRSTUVWXYZ23456789` and `secrets`. Generate on the server at organisation creation, retry collisions at most 10 times, enforce database uniqueness, and prevent changes after creation. Normalize by trimming, case-folding and normalizing dashes.

Only the owner and that organisation's clients can see the code. Public lookup returns only `{name, city, state, business_type}` for verified, active organisations. Invalid/inactive/unverified codes return generic `org_not_found`. Throttle lookup to 30/minute/IP.

## 6. Email verification
Both roles must verify before login. Registration creates an unverified account and verification token, then sends `${FRONTEND_URL}/verify-email?token=...`. Verification consumes a single-use token. Resend always returns the same 202 body for known and unknown accounts; throttle to one per 60 seconds per email/IP and five per hour. Unverified owners' organisations are not discoverable. Login for an unverified user returns `403 email_not_verified` and the UI offers resend.

Use console or file-based email in development/E2E; E2E reads the latest `.eml` to extract links, never the database. `purge_unverified --days 7` removes stale unverified accounts and empty organisations. Password reset uses the same token model; forgot-password responses are generic and throttled.

## 7. Authentication and roles
`POST /auth/login/` accepts `{email, password, portal}` with `portal` equal to `client` or `organisation`. Bad credentials return generic `invalid_credentials`; a valid account on the wrong portal returns `403 wrong_portal` with a friendly hint. Tokens remain in httpOnly cookies via the Next.js BFF. Access claims may include role and organisation ID, but every request derives tenant from the database user, never a client-supplied tenant ID. Password minimum length is 10 and Django validators apply.

## 8. Tenancy rules
1. Tenant is always `request.user.organisation`; no endpoint accepts an organisation ID except public Org Code lookup and client registration.
2. Every tenant model query (Staff, Service, WorkingHours, Booking, Client) uses a shared `TenantQuerySet.for_org()` and DRF `TenantScopedMixin`; no ad-hoc scoping.
3. Cross-tenant object access returns 404, not 403.
4. Router introspection fails if a non-public view is not tenant-scoped or on a justified allow-list.
5. Clients see their own bookings in full; other bookings expose only `booked` slot state, never personal data.
6. Organisation admins see only their organisation's data.

## 9. Booking behavior
Booking requires an authenticated client; organisation and client derive from auth. Payload is `{staff, service, date, start_time}`. An organisation admin may book on behalf of a registered client in the same organisation.

Cancellation is available to the owning client or organisation admin before the appointment starts. It sets `cancelled_at` and `cancelled_by`, clears `active_slot`, reopens the slot and emails the client naming who cancelled. Only organisation admins may mark completed/no-show, only from confirmed and after the appointment starts.

Buffer, lead time, booking window and timezone come from Organisation; environment values are defaults for new organisations. The existing lock-first concurrency contract is unchanged: `transaction.atomic`, lock Staff first, use locking reads, interval overlap checks, catch `IntegrityError`, retry MySQL deadlocks, send email via `transaction.on_commit`.

An organisation without active services or staff returns `org_not_ready` and a friendly screen. Deactivated staff are hidden from clients but future bookings remain and the owner sees a count warning.

### 9.1 Slot grid states
`GET /staff/<id>/slots/?date=&service=` returns date, timezone, `day_status`, `message_params`, `available_count`, `next_available` and `slots`. Each slot has start/end and state: `available`, `booked` (any other client's overlap), or `mine` (current client's booking). Past and inside-lead-time slots are omitted. Booking rechecks availability inside the lock; the grid is advisory.

`day_status` is one of `open`, `fully_booked`, `closed_day`, `all_passed`, `too_soon`, `outside_window`, `past_date`, `staff_unavailable`, `service_unavailable`, `not_configured`. If there are no available slots, `next_available` points to the nearest bookable slot in the window or null. Use batched queries rather than per-day query loops.

## 10. API contract
Base path `/api/`; error envelope remains `{code, detail, fields}`. New codes: `email_taken`, `email_not_verified`, `wrong_portal`, `invalid_credentials`, `token_expired`, `token_invalid_or_used`, `org_not_found`, `org_not_ready`, `weak_password`.

| Area | Endpoint | Contract |
|---|---|---|
| Public | `GET /orgs/lookup/?code=` | Verified active organisation summary only; throttled |
| Registration | `POST /auth/register/organisation/` | Owner and organisation details; returns verification-sent response |
| Registration | `POST /auth/register/client/` | Client details plus Org Code; returns verification-sent response |
| Verification | `POST /auth/verify-email/`, `/auth/resend-verification/` | Consume token / generic 202 resend |
| Auth | `POST /auth/login/`, `/auth/refresh/`, `/auth/logout/` | Portal-aware login; cookie contract retained |
| Profile | `GET/PATCH /auth/me/` | Edit name/phone; email read-only; include role-appropriate organisation summary |
| Password | `/auth/password/forgot/`, `/reset/`, `/change/` | Generic forgot response; token-based reset |
| Organisation | `GET/PATCH /org/` | Owner only; code read-only |
| Client booking | `GET /services/`, `/staff/`, `/staff/<id>/slots/`, `/staff/<id>/availability/` | Authenticated and tenant-scoped |
| Client booking | `POST /bookings/`, `GET /bookings/mine/?scope=upcoming\|past`, `PATCH /bookings/<id>/cancel/` | Client identity/tenant from auth |
| Admin | `GET /admin/bookings/`, `POST /admin/bookings/` | Tenant-scoped list and on-behalf booking |
| Admin | `PATCH /bookings/<id>/status/`, `GET /admin/clients/` | Status controls and searchable clients |
| Admin | CRUD `/admin/staff/`, `/admin/services/`; working-hours, stats, staff-availability routes | Tenant-scoped management |

The full request/response details and screen acceptance criteria are specified in the originating CR-01 request pack. Regenerate `docs/openapi.yaml` from drf-spectacular when these endpoints are implemented.

## 11. Information architecture
Public logged-out navigation order: Brand, Home, Book Now, Register as Client, Log in, Register as Organisation (the only filled button). No health/status indicator in UI. Logged-out Book Now shows a login/register gate. On mobile, use the same order in a menu sheet with Register as Organisation pinned primary.

Client navigation: organisation name as brand; Home, Book Now, My Bookings, avatar menu (Profile, Log out). Organisation navigation: solid sidebar in order Dashboard, Bookings, Clients, Staff, Services, Profile; floating toolbar with date navigation, command palette and avatar.

Routes: public `/`, `/book`, `/register/client`, `/register/organisation`, `/login`, `/check-email`, `/verify-email`, `/forgot-password`, `/reset-password`; client `/book`, `/book/confirmation`, `/bookings`, `/profile`; admin `/dashboard`, `/dashboard/bookings`, `/dashboard/clients`, `/dashboard/staff`, `/dashboard/services`, `/dashboard/profile`. Server layouts enforce role redirects after loading `/auth/me`; middleware checks cookie presence only.

## 12. Screen requirements
Home is concise, with client and salon paths, a three-step explanation, and benefits without invented statistics or testimonials. Registration forms validate inline and support prefilled Org Code lookup. Check-email supports resend cooldown. Verification shows verifying/success/expired/invalid states. Login has Client/Organisation segmented control and clear wrong-portal/unverified feedback.

Client booking is Service → Staff → Date & Time → Confirm; profile data is read-only at confirmation. Selecting a date immediately loads its slots. Available slots are white, selected accent, booked soft green with “Booked” and check icon, and own bookings green with accent ring and “Your booking”. Include legend, accessible unavailable-day messaging and next-available action. Confirmation links to My Bookings and another booking. My Bookings has Upcoming/Past, confirmed cancellation dialog and useful empty state. Profile shows verified email, phone, organisation and read-only Org Code with copy action.

Admin dashboard has KPI summary, staff-column calendar, availability and up-next. Bookings are green cards with client name, service and time. Completed is slate, no-show red, cancelled hidden by default. Drawer supports details and status actions, with destructive cancellation separated and confirmed. Admin can create on behalf, filter/search bookings, inspect clients and manage staff/services/hours/profile. Org profile exposes code copy/invite actions and booking settings. Welcome card includes code and onboarding checklist.

## 13. Design deltas
Keep existing soft-minimal, Bento, selective-glass language, tokens, typography, radii, motion and accessibility principles. Green means booked/confirmed: `--booked-bg #E8F6EE`, `--booked-border #BFE3CE`, `--booked-text #0B6B47`. Completed uses slate, no-show red, cancelled grey with strikethrough; indigo remains primary action/selection only.

Simplify: fewer cards/borders/words, prefer rows for lists. One filled primary button per view region. Header title left/action right; secondary actions in overflow. Flows use Back left and Continue right; mobile uses sticky bottom bar. Destructive actions are separated, never primary, and confirmed. Form submit is full-width mobile/right-aligned desktop. Icon-only buttons have tooltip and accessible name; do not duplicate actions. Keep glass limited to nav pill, mobile booking bar, dashboard toolbar/drawer header, and command palette. Respect reduced motion and WCAG 2.2 AA; test responsive sizes from 320px through 1440px.

## 14. Availability and auth copy catalogue
Availability text is implemented as typed functions in `frontend/src/lib/copy/availability.ts`, with unit tests for each state:

| State | Message/action |
|---|---|
| `closed_day` | “{Staff} isn't working on {weekday}s”; choose another day or staff; link to next date |
| `fully_booked` | “All times on {date} are booked”; show number open on next date and jump there |
| `all_passed` | “Today's appointments have passed”; view tomorrow |
| `too_soon` | “The remaining times today are too soon to book”; explain lead-time and view tomorrow |
| `outside_window` | State maximum booking window; return to a valid date |
| `past_date` | Explain date passed; return to today |
| `staff_unavailable` | Staff not taking bookings; choose another |
| `service_unavailable` | Staff does not offer service; choose another |
| `not_configured` | Schedule not set up; check later or choose another |
| `org_not_ready` | Organisation setup incomplete; contact salon if phone exists |
| `slot_unavailable` | “That time was just taken”; refresh and focus nearest open slot |
| Network error | “We couldn't load times”; retry |

Use staff first name, weekday and formatted dates. Auth messages include check-inbox, expired-link, verified-success, and friendly wrong-portal text.

## 15. Security and non-functional requirements
Tenant isolation is demonstrated by matrix and router-introspection tests. Hash/expire email tokens. Prevent account enumeration on login, resend and forgot-password. Registration may disclose `email_taken` as a documented UX trade-off and is throttled. Throttle login (10/min/IP), registration (5/hour/IP), Org Code lookup (30/min/IP), and resend (per-email cooldown). Sanitize Org Code input. Emails include organisation name/contact details. Never log PII or tokens. Preserve concurrency guarantees and WCAG/Lighthouse targets.

## 16. Decisions to record
Record these deviations in `docs/DECISIONS.md`: (8) single tenant → Organisation tenant; (9) no-login customers → verified client accounts with Org Code; (10) Admin/Staff roles → `org_admin`/`client`, staff are non-login profiles; (11) form customer fields → client FK plus immutable snapshot; (12) cancel token → account-authorized cancellation; (13) env-level rules → per-organisation settings; (14) hidden/struck booked slots → green booked cards.

## Migration strategy
Fresh database: apply the final schema migrations in dependency order and migrate directly to a fully tenant-aware schema. Existing database: create an explicitly identified Demo Organisation; add nullable tenant/user relationship fields; backfill all existing services, staff, bookings and users into that organisation; map legacy admin users to `org_admin`; detach legacy staff logins (`Staff.user = NULL`) and deactivate them; preserve booking snapshots; remove cancel tokens; then enforce non-null tenant/client constraints. Keep migrations linear and reversible where practical. Prove both paths in M1 tests before release.
