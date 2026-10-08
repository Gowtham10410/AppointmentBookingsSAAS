# PRODUCT SPEC — CR-01 merged

## Current contract
The product is multi-organisation. Owners are verified `org_admin` accounts; customers are verified `client` accounts permanently attached to one organisation through an Org Code. Public no-login booking and staff login are removed. Tenant scope always comes from the authenticated user, and cross-tenant access returns 404. Booking snapshots client details and retains the lock-first slot engine and `active_slot` uniqueness guarantee. Organisation booking settings are tenant-specific. The complete requirements and acceptance criteria are in [`CR01_MULTI_ORG.md`](CR01_MULTI_ORG.md), which takes precedence when detail is needed.

The customer flow is Service → Staff → Date & Time → Confirm. Slots distinguish available, booked and the client's own booking; booked/confirmed states use green. Owners manage bookings, clients, staff, services and working hours in an organisation-scoped dashboard. Email verification is required before either portal can log in.

## Historical baseline (superseded in full where it conflicts with CR-01)
The sections below record the original single-tenant product baseline only. They are not current requirements. In particular, CR-01 §§2–10 supersede their user roles, scope, data model, slot API, authentication, cancellation and settings contracts; CR-01 §§11–16 define current information architecture, UI and security requirements.

## 1. Users and goals
| Role | Auth | Goal |
|---|---|---|
| Customer | None (no account) | See real availability, book in under a minute, receive confirmation, cancel if plans change |
| Staff | Login | See and manage only their own schedule; mark bookings completed / no-show |
| Admin | Login | Configure staff, services, working hours; see and manage all bookings |

## 2. Scope
In scope: staff / service / working-hours management; slot generation; conflict-free booking; email confirmation; cancellation (tokenised link or dashboard) that reopens the slot; role-based dashboard with filters; status updates; simple counts-based KPIs.
Out of scope: multi-tenancy, payments, ML/forecasting, SMS, rescheduling UI, recurring appointments, multi-service carts, native mobile app.

## 3. Domain model (final)
All primary keys are `BigAutoField`. Database: MySQL InnoDB, `utf8mb4`.

User (`accounts.User`, extends `AbstractUser`): `role` ∈ {`admin`, `staff`}, default `staff`. Email unique and required. Login by email.

Staff (`scheduling.Staff`): `user` OneToOne; `specialization` (≤100, blank ok); `is_active` (default True); `services` ManyToMany to Service, `blank=True` — empty means "offers all active services".

Service: `name` (≤100); `description` (text, blank ok); `duration_minutes` (5–480, multiple of 5); `price` Decimal(8,2) ≥ 0; `is_active` (default True).

WorkingHours: `staff` FK; `day_of_week` 0–6 (Mon=0); `start_time`; `end_time` (must be > start); `is_off_day` (default False). Unique (staff, day_of_week). A missing row means the staff member does not work that day.

Booking: `staff` FK (PROTECT), `service` FK (PROTECT), `customer_name` (≤100), `customer_email`, `customer_phone` (≤15), `date`, `start_time`, `end_time`, `status` ∈ {`confirmed`, `cancelled`, `completed`, `no_show`}, `created_at`, plus `cancel_token` (random URL-safe string, unique, never logged) and `active_slot` (nullable small int, see §5). Indexes: `(staff, date)`, `(date, status)`. Human reference: `SAS-` + zero-padded id, e.g. `SAS-000042` (derived, not stored).

## 4. Slot rules (single source of truth)
Settings (env-driven): `BUFFER_MINUTES=10`, `MIN_LEAD_MINUTES=30`, `BOOKING_WINDOW_DAYS=30`, `BUSINESS_TZ=Asia/Kolkata`.

`generate_slots(staff, date, service)` returns start/end pairs:
1. Reject if staff or service is inactive, staff does not offer the service, `date` is outside `[today, today + BOOKING_WINDOW_DAYS]`, there is no `WorkingHours` row for the weekday, or `is_off_day` is true.
2. Starting at `start_time`, emit candidates every `duration + BUFFER_MINUTES` minutes while `candidate_end <= end_time`.
3. Drop candidates that start earlier than `now + MIN_LEAD_MINUTES` (business timezone) when `date` is today.
4. Drop candidates whose interval overlaps any non-cancelled booking for that staff and date. Overlap test: `cand_start < b.end_time AND cand_end > b.start_time`.

## 5. Concurrency contract (the project's core claim)
`book_slot(...)` must guarantee that no two non-cancelled bookings for the same staff overlap, even under simultaneous requests.

1. `@transaction.atomic`.
2. First statement in the transaction: lock the `Staff` row with `select_for_update()`. This serialises all bookings per staff member.
3. Re-run the slot check inside the lock. Use locking reads (or `READ COMMITTED` isolation, set explicitly in `DATABASES["default"]["OPTIONS"]["init_command"]`). Do not do an unrelated plain `SELECT` before acquiring the lock. Under REPEATABLE READ that would create a stale snapshot and defeat the lock.
4. The requested `start_time` must be one of the freshly generated slots. This single check enforces the working-hours grid, off-days, past times, window and overlap.
5. Insert the booking with `active_slot = 1`.
6. Catch `IntegrityError` and return the same "slot unavailable" result. The database constraint is the last line of defence.
7. Retry at most 2 times on MySQL deadlock (error 1213). Then fail with 409.
8. Send the email only via `transaction.on_commit`.

Database constraint: `unique_together = (staff, date, start_time, active_slot)`.
`active_slot = 1` while status ≠ `cancelled`, and `NULL` when cancelled. MySQL treats `NULL`s as distinct in unique indexes, so a cancelled booking no longer blocks the slot. Maintain `active_slot` in one place, a `Booking.set_status()` method plus `save()` guard, and test it.

## 6. API contract
Base path `/api/`. JSON only. Dates `YYYY-MM-DD`, times `HH:MM`, money as string.

Error envelope (every non-2xx):
```json
{ "code": "slot_unavailable", "detail": "That time was just taken. Please choose another slot.", "fields": {} }
```
Codes: `validation_error` (400, `fields` populated) · `unauthorized` (401) · `forbidden` (403) · `not_found` (404) · `slot_unavailable` (409) · `booking_not_cancellable` (409) · `rate_limited` (429).

### Public (no auth)
| Method | Path | Notes |
|---|---|---|
| GET | `/services/` | Active services |
| GET | `/staff/?service=<id>` | Active staff who offer the service (all active staff if param omitted) |
| GET | `/staff/<id>/slots/?date=&service=` | `{ date, timezone, slots:[{start_time,end_time}] }` |
| GET | `/staff/<id>/availability/?service=&from=&to=` | `{ next_available:{date,start_time}\|null, days:[{date,status:"open"\|"full"\|"off"\|"past",available_count}] }` (max 31 days) |
| POST | `/bookings/` | Body: `staff, service, date, start_time, customer_name, customer_email, customer_phone`. 201 returns booking + `reference` + `cancel_token`. 409 `slot_unavailable`. Throttled. |
| GET | `/bookings/lookup/?token=` | Booking details by cancel token |
| PATCH | `/bookings/<id>/cancel/` | Allowed with `?token=<cancel_token>` or authenticated admin / owning staff. Sets `cancelled`, clears `active_slot`, reopens slot. 409 `booking_not_cancellable` if already completed / no-show / cancelled / in the past. |

### Auth
`POST /auth/login/` (email, password) → sets tokens · `POST /auth/refresh/` · `POST /auth/logout/` · `GET /auth/me/` → `{id, email, name, role, staff_id|null}`.

### Admin and staff
| Method | Path | Who |
|---|---|---|
| GET | `/admin/bookings/` | Admin only. Filters: `date`, `date_from`, `date_to`, `staff`, `status`, `q` (name / email / phone / reference), `ordering`, pagination |
| GET | `/staff/me/bookings/` | Staff, own only. Same filters and serializer |
| PATCH | `/bookings/<id>/status/` | Body `{status}` ∈ `completed`, `no_show`, `cancelled`. Admin: any booking. Staff: own bookings only. Only from `confirmed`. Completed / no-show only once the start time has passed. |
| CRUD | `/admin/staff/`, `/admin/services/` | Admin only. Soft-deactivate via `is_active`; never hard-delete rows referenced by bookings |
| GET/PUT | `/admin/staff/<id>/working-hours/` | Admin; staff may edit own only if `STAFF_CAN_EDIT_OWN_HOURS=true`. PUT replaces the full week atomically |
| GET | `/admin/stats/?date=` | Counts only: `today_total`, `upcoming_confirmed`, `completed`, `no_show`, `cancelled`. |
| GET | `/admin/staff-availability/?date=` | Per staff: working window, booked minutes, free minutes, utilisation %, next free slot |

Staff users may also call the stats and availability endpoints, scoped to themselves.

### Permission matrix
| Capability | Customer | Staff | Admin |
|---|---|---|---|
| Browse slots, book | ✅ | ✅ | ✅ |
| Cancel via token | ✅ | — | — |
| View all bookings | ❌ | ❌ | ✅ |
| View own bookings | — | ✅ | ✅ |
| Mark completed / no-show / cancel | ❌ | own | all |
| Manage staff, services | ❌ | ❌ | ✅ |
| Edit working hours | ❌ | policy flag | ✅ |

## 7. Validation rules
Customer name 2–100 chars. Email RFC-valid. Phone: strip spaces and dashes, then `^\+?\d{10,14}$`. Date not in the past. Start time must be one of the generated slots. Service and staff must be active and compatible. Inputs are trimmed. Server validation is authoritative, and the frontend mirrors it with zod.

## 8. Notifications
Confirmation email (HTML + plain text) after commit: reference, service, staff, date, time, customer name, and a "Manage or cancel" link to `${FRONTEND_URL}/booking/manage?token=...`. Console email backend by default, SMTP via env. Email failures are logged and never fail the booking. A short cancellation email is sent on cancellation.

## 9. Environment variables (`.env.example`)
`DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, BUSINESS_TZ, BUFFER_MINUTES, MIN_LEAD_MINUTES, BOOKING_WINDOW_DAYS, STAFF_CAN_EDIT_OWN_HOURS, EMAIL_BACKEND, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL, CORS_ALLOWED_ORIGINS, FRONTEND_URL, BACKEND_INTERNAL_URL, NEXT_PUBLIC_BUSINESS_NAME, COOKIE_SECURE`.

## 10. Non-functional targets
- Slots endpoint p95 < 150 ms locally with seeded data.
- Booking under 10 simultaneous identical requests: exactly 1 success, 9 × 409, 0 duplicate rows.
- Lighthouse mobile: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95.
- WCAG 2.2 AA. Works from 320px width upward.

## 11. Deliberate deviations from the project report (record these in DECISIONS.md)
| # | Report said | Product does | Why |
|---|---|---|---|
| 1 | Public page = HTML/CSS/JS, dashboard = Django templates | Next.js + React + TypeScript frontend consuming the DRF API | Modern UX target |
| 2 | `unique_together (staff, date, start_time)` | `(staff, date, start_time, active_slot)` | Lets a cancelled slot be rebooked |
| 3 | Overlap handled by equal start time | Interval-overlap check inside the lock | Different service durations can overlap with different start times |
| 4 | Lock the `WorkingHours` row | Lock the `Staff` row first | Always exists; serialises per staff |
| 5 | Django session auth | JWT in httpOnly cookies via Next route handler (BFF) | Clean SPA-style auth with no token in JS |
| 6 | `Service` had no active flag; no `Staff`↔`Service` link | Added `Service.is_active`, `Staff.services` (empty = all) | Report's abstract says staff "offer" services |
| 7 | Cancel link "via token" | `Booking.cancel_token` + `reference` | Concrete implementation of the documented idea |
