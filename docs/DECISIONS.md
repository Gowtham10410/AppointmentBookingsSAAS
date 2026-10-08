## Decision 19 — Give Staff profiles an independent display name
- Decision: Add required `Staff.name` and backfill it from the linked legacy user's full name or email before detaching staff login accounts.
- Reason: Staff become non-login profiles, but booking cards, slot selection and admin views still need a stable display name independent of a User relation.
- Alternatives considered: Keep deriving names from `Staff.user`; rejected because the new model permits `user=NULL`.
## Decision 11 — Move from single-tenant to Organisation tenancy
- Decision: Each business is an `Organisation`; all users, staff, services and bookings belong to exactly one organisation.
- Reason: Salons need isolated customer and schedule data while sharing one product deployment.
- Alternatives considered: Continue single-tenant; rejected because it cannot support multiple independent salons.

## Decision 12 — Require verified client accounts and Org Codes
- Decision: Replace public no-login booking with verified client registration using the organisation's unique Org Code.
- Reason: The salon serves existing customers and needs bookings attached to a durable client identity and organisation.
- Alternatives considered: Public booking with customer form fields; rejected because tenant membership and client booking history would be unverifiable.

## Decision 13 — Replace Admin/Staff roles with org_admin/client
- Decision: Use `org_admin` and `client` login roles; Staff are non-login profiles managed by the organisation owner.
- Reason: The requested product has two portals and does not require individual staff authentication.
- Alternatives considered: Preserve staff logins; rejected as unnecessary scope and UI complexity.

## Decision 14 — Link bookings to clients and preserve snapshots
- Decision: Each booking references a same-organisation client and also stores immutable customer detail snapshots.
- Reason: Client identity enables privacy-safe booking lists while snapshots preserve historical details after profile edits.
- Alternatives considered: Store only free-form booking details; rejected because identity and organisation membership could drift.

## Decision 15 — Replace cancellation tokens with account permissions
- Decision: Clients cancel their own bookings and organisation admins manage bookings in their tenant; remove `cancel_token`.
- Reason: Verified accounts provide ownership checks without a bearer cancellation token.
- Alternatives considered: Keep token cancellation; rejected because account-based authorization is now available.

## Decision 16 — Move booking rules to Organisation settings
- Decision: Buffer, lead time, booking window and timezone are stored per organisation; environment values seed defaults for new organisations.
- Reason: Different salons need independent scheduling policies.
- Alternatives considered: Retain global environment settings; rejected because one business's settings would affect every tenant.

## Decision 17 — Use green for booked/confirmed slots
- Decision: Render booked and own-booking slots as green cards, with a distinct accent ring for the client's own booking; use slate for completed, red for no-show and grey for cancelled.
- Reason: The requested calendar makes booked availability immediately scannable while preserving status distinctions.
- Alternatives considered: Hide or strike through booked slots; rejected because clients need to see taken times without seeing other clients' identities.

## Decision 18 — Permit explicit duplicate-email feedback at registration
- Decision: Registration may return `email_taken`; login, resend and forgot-password remain generic and avoid account enumeration.
- Reason: The registration UX needs actionable correction when a user submits an already-used address, while recovery endpoints must not expose account existence.
- Alternatives considered: Make registration fully generic; deferred because it creates a less clear onboarding error and CR-01 explicitly permits this trade-off.
# Decisions log

## Decision 1 — Move from Django templates to Next.js frontend
- Decision: Build the public UI and dashboard in Next.js + React + TypeScript, with DRF as the backend API.
- Reason: The project brief targets a modern SPA experience and a JavaScript-first dashboard workflow. This is cleaner for booking UX, complex client-side state and responsive interactions.
- Alternatives considered: Keep Django templates and static JS; reject because it does not match the product brief or modern UX expectations.

## Decision 2 — Use `(staff, date, start_time, active_slot)` instead of a simple slot uniqueness constraint
- Decision: Keep the database uniqueness constraint scoped by `active_slot` so cancelled bookings do not block rebooking.
- Reason: A cancelled booking must reopen the same slot, which is impossible with a plain `(staff, date, start_time)` unique index.
- Alternatives considered: Reusing the same booking row or soft-deleting without `active_slot`; reject because they either lose auditability or keep stale blocking rows.

## Decision 3 — Use interval-overlap validation rather than equal-start-time checks
- Decision: Treat bookings as overlapping whenever `cand_start < b.end_time AND cand_end > b.start_time`.
- Reason: Different service durations can create overlaps even when the start times differ, so equal-start comparisons are insufficient.
- Alternatives considered: Start-time-only comparisons; reject because they fail real-world duration combinations.

## Decision 4 — Lock the `Staff` row instead of `WorkingHours`
- Decision: Lock the `Staff` row with `select_for_update()` as the first transaction statement.
- Reason: The staff record always exists and serialises all booking attempts for that staff without excessive locking.
- Alternatives considered: Locking `WorkingHours`; reject because it is a weaker and less stable boundary than the staff-level schedule.

## Decision 5 — Use JWT in httpOnly cookies via a Next BFF
- Decision: Keep tokens out of browser JavaScript and pass them via cookie-based BFF route handlers.
- Reason: This matches a clean SPA-style auth setup while reducing token exposure and keeping auth flows safer.
- Alternatives considered: Frontend local storage or direct token storage; reject because they are more exposed to XSS and worse for security posture.

## Decision 6 — Add `Service.is_active` and `Staff.services` relationship
- Decision: Model service activation and staff-service compatibility explicitly.
- Reason: The spec states that a staff member can offer a subset of services and that an empty relationship means they offer all active services.
- Alternatives considered: Hard-coding service lists or skipping the relationship; reject because it breaks the domain model and soft-deactivation rules.

## Decision 7 — Use `cancel_token` + `reference` for manage links
- Decision: Generate a unique cancel token and expose a human-readable booking reference for customer-facing flows.
- Reason: This gives a stable, safe cancellation path without exposing booking IDs or making cancellation a database enumeration vector.
- Alternatives considered: Only use raw numeric IDs or session-based cancel flows; reject because they are less user-friendly and weaker on security.

## Decision 8 — Keep Django settings inheritance via the base settings module and suppress the star-import false positives explicitly
- Decision: Keep `config.settings.test` and `config.settings.prod` importing from `config.settings.base` and overriding environment-specific values, rather than recreating the full settings file by hand.
- Reason: The project relies on the shared Django app registry, middleware, URL config and auth settings defined in the base file. Rebuilding those values manually breaks `INSTALLED_APPS` and makes the project fail at import time. Ruff reports false positives for star imports in Django settings files, so the clean fix is a file-level `ruff: noqa` while preserving the valid inheritance pattern.
- Alternatives considered: Re-define each setting manually or disable the settings inheritance; reject because both options create drift and break Django app startup.

## Decision 9 — Use a service-layer slot generator and lock-first booking path
- Decision: Treat `generate_slots` and `book_slot` as a dedicated scheduling service layer that validates the working-hours grid, buffer rules and overlap semantics before creating a booking.
- Reason: The product spec requires the same slot-calculation logic to be used for both display and booking validation. Putting that logic in a single service layer avoids drift between the public slot API and the internal booking guarantee.
- Alternatives considered: Inline the logic into models or views; reject because it couples business rules to persistence and makes concurrency bugs easier to miss.

## Decision 10 — Accept both `HH:MM` and `HH:MM:SS` values in the slot engine
- Decision: Normalise all incoming slot times via a parser that accepts both common string forms produced by Django/DRF and business inputs.
- Reason: DRF serialisation can surface a `time` object as `09:00:00`, and the slot engine must treat that as equivalent to `09:00` during booking validation.
- Alternatives considered: Force the frontend to emit only `HH:MM` strings; reject because it creates a brittle contract between API payloads and backend validation.
