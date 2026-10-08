# DESIGN SYSTEM — "Soft Minimal SaaS, with depth"

## CR-01 amendments (current)
Keep the established soft-minimal, Bento and selective-glass visual language and compatible typography, radii, motion and accessibility rules below. Where an older section conflicts with this amendment, CR-01 is authoritative; the previous five-step booking blueprint and its details form step are superseded by CR-01 §§11–13.

- Green means booked/confirmed: `--booked-bg: #E8F6EE`, `--booked-border: #BFE3CE`, `--booked-text: #0B6B47`. Completed is slate, no-show red, and cancelled grey with strikethrough. Indigo is reserved for primary actions and selection.
- Client booking is Service → Staff → Date & Time → Confirm. Available slots are white, selected slots use the primary accent, booked slots are green and unavailable, and the client's own booking is green with an accent ring. Every state has text/icon support and a legend.
- Logged-out navigation order is Brand, Home, Book Now, Register as Client, Log in, Register as Organisation; only the last item is filled. Client and owner navigation follow CR-01 §11. Do not show API health or system status in UI.
- Use one filled primary action per view region. Place header actions at the right, Back/Continue at opposite ends, destructive actions apart and confirmed, and form submits full-width on mobile/right-aligned on desktop. Icon-only actions need tooltips and accessible names; do not duplicate actions.
- Reduce cards, borders and copy. Prefer rows for lists. Green must not be used to imply any state other than booked/confirmed (except success feedback). Preserve reduced-motion, keyboard access, responsive layout and WCAG 2.2 AA requirements.

See [`CR01_MULTI_ORG.md`](CR01_MULTI_ORG.md) §§11–14 for complete navigation, screen behavior, button rules and copy catalogue.

## 1. Design thesis
Modern soft-minimal SaaS with subtle depth, Bento structure, selective Liquid Glass, and polished micro-interactions. Vercel/Linear cleanliness, Apple-inspired softness. Prioritise clarity, speed and mobile-first booking UX over decoration.

Style budget: 60% soft minimalism, 15% spatial / layered UI, 10% Bento, 10% Liquid Glass, 5% motion delight.

## 2. Tokens (Tailwind v4 `@theme` + shadcn CSS variables)
Light default tokens:
- `--bg`: `#FAF9F7`
- `--surface`: `#FFFFFF`
- `--surface-2`: `#F4F2EE`
- `--border`: `#E8E5DF`
- `--text`: `#1C1B19`
- `--text-muted`: `#6B675F`
- `--accent`: `#4F46E5`
- `--accent-soft`: `#EEF0FF`
- `--success`: `#0F7B53`
- `--warning`: `#B45309`
- `--danger`: `#C2362B`

Dark mode: define the full token set under `.dark`.

Radii: inputs and buttons 14px; cards 20px; drawers/sheets top 24px; pills 9999px.
Spacing: 4px base; gutters 16/24/40; Bento gap 16/20.
Elevation: Tier 0 canvas, Tier 1 card, Tier 2 floating.

## 3. Typography
Font: Geist Sans plus Geist Mono fallback. Use font-variant-numeric: tabular-nums.

| Role | Size / line | Weight | Tracking |
|---|---|---|---|
| Display | 40 / 44 | 600 | −0.02em |
| H1 | 30 / 36 | 600 | −0.015em |
| H2 | 22 / 28 | 600 | −0.01em |
| H3 | 17 / 24 | 600 | 0 |
| Body | 15 / 24 | 400 | 0 |
| Small | 13 / 20 | 500 | 0 |
| Micro / eyebrow | 12 / 16 | 600, uppercase | +0.04em |

## 4. Liquid Glass — strict usage rules
Allowed surfaces only: customer floating nav pill, mobile sticky booking bar, dashboard floating toolbar, command palette.
Recipe: `bg-white/70 backdrop-blur-xl backdrop-saturate-150 border border-white/60` + Tier-2 shadow + 1px inner top highlight. Provide a solid fallback via `@supports not (backdrop-filter: blur(1px))`.
Never put glass behind paragraphs, forms or table rows. Create a single `<Glass>` primitive.

## 5. Motion
Wrap the app in `<MotionConfig reducedMotion="user">`.
- Springs: UI `{ type: "spring", stiffness: 420, damping: 34 }`; gentle `{ stiffness: 260, damping: 30 }`.
- Durations: micro 120–180ms; transitions 220–320ms; confirmation 600–900ms.
- Patterns: selected slot/date/service use shared `layoutId`, booking steps use `AnimatePresence`, buttons `scale 0.98`, KPI count-up once, lists stagger 30ms, confirmation ring pulse, drawer spring slide.
- Animate only `transform` and `opacity`.

## 6. Components to build
`Glass` · `AppNavPill` · `BentoGrid` / `BentoCard` · `ServiceCard` · `StaffCard` · `DatePill` / `DateScroller` · `TimeSlotPill` · `TimeSlotGroup` · `BookingSummary` · `Stepper` · `KpiCard` · `StatusBadge` · `StaffAvailabilityBar` · `AppointmentDrawer` · `FilterPill` / `FilterBar` · `DataTable` · `EmptyState` · `ErrorState` · `Skeleton` variants · `ConfirmDialog` · `CommandPalette` · `SuccessCheck`.
A dev-only `/design` kitchen-sink route renders every component in every state.

## 7. Customer experience blueprint (`/book`)
The customer flow is: Service → Staff → Date & Time → Details → Confirm.
The booking bar is sticky and glassy on mobile. Step and selections live in query params.

## 8. Business dashboard blueprint (`/dashboard`)
A solid collapsible left sidebar plus floating glass toolbar over the content. Overview is a 12-column bento grid with KPI cards, a calendar workspace, staff availability and up-next list. Appointments open in a right-side drawer. A command palette uses `⌘K`.

## 9. States and quality
All data views include loading, empty and error states. Toasts via sonner after actions.

## 10. Accessibility checklist
Landmarks and headings in order; slot and date pickers as radiogroups with roving tabindex; `aria-live="polite"` announcements; visible 2px accent focus ring; forms with `aria-describedby`; colour not the only status signal; contrast >= 4.5:1; reduced-motion variant; >=44px targets; zoom to 200% with no horizontal scroll.

## 11. Visual QA checklist
Alignment on the 4px grid; consistent radii; only one accent colour; glass only in four allowed places; type scale respected; no orphaned shadows; icons from Lucide at consistent sizes; tested at 320, 390, 768, 1024, 1440px; light and dark intentional.
