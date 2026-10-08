# Architecture

## System diagram

```mermaid
flowchart LR
    Browser[Browser / Customer / Staff / Admin] --> Next[Next.js App Router Frontend\nBFF + API proxy]
    Next --> DRF[Django + DRF + business logic]
    DRF --> MySQL[(MySQL 8.x / InnoDB)]
    DRF --> Email[Email Service / Console SMTP]
    Browser --> Public[Public booking flow]
    Browser --> Dashboard[Business dashboard]
```

## Core booking flow

```mermaid
sequenceDiagram
    participant C as Customer
    participant F as Frontend / BFF
    participant D as Django Service Layer
    participant M as MySQL
    participant E as Email

    C->>F: Submit booking
    F->>D: POST /api/bookings/
    D->>M: BEGIN
    D->>M: SELECT staff FOR UPDATE
    D->>M: locking read / re-evaluate slot availability
    alt slot still free
        D->>M: INSERT booking with active_slot=1
        D-->>F: 201 Created
        D->>E: transaction.on_commit -> send confirmation email
    else conflict
        D-->>F: 409 slot_unavailable
    end
    M-->>D: commit
```

## Concurrency design notes
- The `Staff` row is locked first inside `@transaction.atomic`.
- This serialises concurrent booking attempts per staff member, preventing overlapping confirmations.
- Re-running the slot check inside the lock ensures the list of valid slots reflects fresh database state rather than a stale snapshot from an earlier read.
- `active_slot` is only set when a booking is active. When a booking is cancelled, `active_slot` becomes `NULL` and the unique index no longer blocks reuse of that slot.
- The database uniqueness constraint acts as the final defence against races that bypass the service-layer logic.
