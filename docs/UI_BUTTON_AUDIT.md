# UI Button Audit

Baseline captured during CR-01 M0 from the current Django templates and registered Django admin. This records existing controls before CR-01; the **After** column is intentionally reserved for M7. Template links are included because they perform navigation/actions even when styled as buttons.

| Screen | Current control / link | Before: placement and behavior | After (complete in M7) |
|---|---|---|---|
| Shared public header (`/`, `/book/`, confirmation) | Brand: “Smart Appointment Scheduler” | Left side of sticky header; links to `/` | — |
| Shared public header (`/`, `/book/`, confirmation) | “Home” | First nav link; links to `/` | — |
| Shared public header (`/`, `/book/`, confirmation) | “Book now” | Nav link; links to `/book/` | — |
| Shared public header (`/`, `/book/`, confirmation) | “API health” | Nav link to `/api/healthz/`; exposes infrastructure status in customer UI | — |
| Shared public header (`/`, `/book/`, confirmation) | “Book an appointment” | Filled CTA at right side of header; links to `/book/` and duplicates the nav booking action | — |
| Home (`/`) | “Book a visit” | Filled hero CTA; links to `/book/` | — |
| Home (`/`) | “Browse services” | Secondary hero link; scrolls to services | — |
| Home (`/`) | “Schedule a consultation” | Secondary section-header action; links to `/book/` | — |
| Home (`/`) | “Book” (each service row/card) | Filled action at the right of each service item; links to `/book/?service=<id>` | — |
| Home (`/`) | No explicit action in empty services state | Informational “No services are active right now.” message | — |
| Booking (`/book/`) | Service selector | Select field auto-submits GET form on change; not a button | — |
| Booking (`/book/`) | Staff selector | Select field auto-submits GET form on change; not a button | — |
| Booking (`/book/`) | Date input | Date field auto-submits GET form on change; not a button | — |
| Booking (`/book/`) | Available slot radio labels | Each generated time is a selectable radio choice; radios are visually hidden inside labels; no explicit legend/action | — |
| Booking (`/book/`) | “Confirm appointment” | Full-width filled submit button in appointment-details panel | — |
| Confirmation (`/booking/<id>/confirmation/`) | “Back home” | Filled action in success panel; links to `/` | — |
| Confirmation (`/booking/<id>/confirmation/`) | “Book another slot” | Secondary action beside primary; links to `/book/` | — |
| Django admin login (`/admin/login/`) | “Log in” | Django-generated form submit | — |
| Django admin User list (`/admin/accounts/user/`) | “Add user” | Django-generated object-add action in page header | — |
| Django admin User list (`/admin/accounts/user/`) | Search field and “Search” | Django-generated list-filter search controls | — |
| Django admin User list (`/admin/accounts/user/`) | “Go” and action selector | Django-generated bulk-action controls, shown when rows/actions are available | — |
| Django admin User list (`/admin/accounts/user/`) | User email links | Django-generated row links to change forms | — |
| Django admin User add/change (`/admin/accounts/user/add/`, object change) | “Save”, “Save and continue editing”, “Save and add another” | Django-generated form actions; availability depends on add/change permissions | — |
| Django admin User change (`/admin/accounts/user/<id>/change/`) | “Delete” and “History” | Django-generated object actions; Delete opens a confirmation screen | — |
| Django admin delete confirmation | “Yes, I’m sure” and “No, take me back” | Django-generated destructive confirm and cancel actions | — |

## Baseline notes
- Current product routes are Django templates: `/`, `/book/`, and `/booking/<id>/confirmation/`. `/admin/` is Django's built-in User administration; there is no custom owner dashboard.
- The shared header has two distinct filled booking CTAs and an API-health link. The homepage includes a hard-coded `4.9/5` proof point. These are recorded as baseline findings, not endorsed CR-01 behavior.
- Service-card “Book” controls repeat by service; this is appropriate to the old flow but will be reassessed against CR-01's one-primary-action-per-region rule.
- Django admin controls are framework-generated and permission-dependent. The list above captures the registered User admin surface; M1 will add Organisation/EmailToken administration and must update this baseline only if a visible admin action changes before M7.
- **After** placements and rationale are intentionally unfilled until the M7 simplification/polish phase.
