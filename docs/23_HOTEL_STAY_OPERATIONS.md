# Hotel Stay Operations

Sprint 10.4 adds the operational layer that begins after a hotel booking is confirmed. It is intentionally smaller than a property-management system and keeps reservation commerce separate from physical occupancy.

## Domain boundaries

- **Booking** remains the authoritative commercial reservation: dates, guest intent, price snapshot, payment relationship, and reserved RoomType inventory.
- **Stay** is the authoritative operational fulfillment: expected arrival, assigned physical rooms, actual check-in, actual check-out, and no-show outcome.
- **RoomType** describes a sellable category. A **Room** is one physical unit within a property.
- **Customer 360** reads Booking, Stay, Payment, and Conversation records; it does not copy Stay state into CRM-owned tables.

A confirmed Booking can coexist with any valid Stay result. For example, `Booking=CONFIRMED` and `Stay=CHECKED_OUT` is expected. Stay operations do not invent new Booking states.

## Commercial inventory and operational occupancy

Daily RoomType inventory remains the source for sellable availability and reservation holds. Physical Room assignment and `AVAILABLE`/`OCCUPIED`/`OUT_OF_SERVICE` state represent operational occupancy only. Check-in, check-out, and no-show never rewrite the commercial inventory counters.

These layers are deliberately separate so a future PMS reconciliation can compare them without silently replacing either source of truth.

## Physical rooms

Each room belongs to one Workspace, Property, and compatible RoomType. Room code is unique within the Property. The minimum operational states are:

- `AVAILABLE`: eligible for assignment and check-in.
- `OCCUPIED`: held by a checked-in Stay.
- `OUT_OF_SERVICE`: unavailable for assignment until explicitly returned to service.

Owner/Admin users may create and edit rooms and explicitly move an unoccupied room between `AVAILABLE` and `OUT_OF_SERVICE`. An occupied room cannot be marked out of service; Sprint 10.4 does not move guests or create maintenance tickets automatically.

## Stay aggregate and lifecycle

One confirmed Booking creates at most one Stay. Creation is idempotent and snapshots the planned arrival/departure dates, customer link, property, and required physical-room count. `BookingItem.quantity` can be greater than one, so a Stay owns multiple room assignments and requires exactly that number before check-in.

The strict state machine is:

```text
EXPECTED -> CHECKED_IN -> CHECKED_OUT
    |
    +--------------------> NO_SHOW
```

There is no generic status patch route. Each transition is an explicit domain operation.

## Room assignment

An assignment is accepted only when every selected room:

- belongs to the same Workspace and Property as the Stay;
- has the Booking's RoomType;
- is active and not out of service or occupied;
- has no active assignment to another Stay; and
- completes the exact `BookingItem.quantity` requirement.

Assignments are transactionally replaced for an expected Stay. Released assignment history is retained for auditability.

## Check-in and concurrency

Check-in requires a still-confirmed Booking and an `EXPECTED` Stay. It locks the Stay, active assignments, and the relevant physical-room rows in deterministic order. PostgreSQL also enforces one active assignment per room through a partial unique index. Only after all validations pass does one transaction mark every room `OCCUPIED`, set the actual timestamp, move the Stay to `CHECKED_IN`, and append the event.

Two concurrent requests for the same room therefore have exactly one winner. Any validation or database conflict rolls back the entire operation.

Early or late arrival is allowed only through this explicit staff operation. The planned dates are preserved and the actual timestamp is recorded. There is no automatic policy decision and AI has no operational write access.

## Check-out and no-show

Check-out is valid only from `CHECKED_IN`. One transaction returns all assigned rooms to `AVAILABLE`, releases their assignments, stores `actual_check_out_at`, moves the Stay to `CHECKED_OUT`, and appends an event. Repeating a successful check-out returns the existing result without duplicating the transition.

No-show is valid only from `EXPECTED`. It releases any provisional room assignments and records `NO_SHOW`; it does not alter Booking confirmation or RoomType inventory. Repeating the operation is deterministic. A checked-in Stay cannot become a no-show.

## API

All routes are Workspace-scoped under `/api/v1/hotel`:

- `GET/POST /rooms`
- `GET/PATCH /rooms/{room_id}`
- `POST /rooms/{room_id}/out-of-service`
- `POST /rooms/{room_id}/available`
- `GET /stays`
- `GET /stays/{stay_id}`
- `POST /bookings/{booking_id}/stay`
- `POST /stays/{stay_id}/assign-room`
- `POST /stays/{stay_id}/check-in`
- `POST /stays/{stay_id}/check-out`
- `POST /stays/{stay_id}/no-show`

Room and Stay lists are bounded, paginated, and deterministically ordered. Arrival, departure, property, and status filters are available without adding dashboard analytics.

## Authorization and tenant isolation

The existing Hotel policy is reused: Workspace members may read operational records, while Owner/Admin users perform room and Stay mutations. Every service query and relationship is Workspace-scoped; composite foreign keys prevent cross-Workspace links, and assignment validation rejects cross-Property or incompatible RoomType selections.

## Audit and Customer 360

Immutable Stay events record `STAY_CREATED`, `ROOM_ASSIGNED`, `ROOM_UNASSIGNED`, `CHECKED_IN`, `CHECKED_OUT`, and `NO_SHOW` with Workspace, Booking, Stay, Property, optional Room, actor, and timestamp. Event metadata is safe and does not duplicate customer content.

Customer 360 includes bounded authoritative Stay summaries and merges Stay events into its journey timeline. The existing repeat-guest rule continues to count confirmed Bookings; Sprint 10.4 does not silently redefine it using completed Stays.

## Known limitations and future seam

- No housekeeping cleanliness workflow, maintenance ticketing, folio, deposits, minibar, charges, refunds, loyalty, key cards, OTA sync, or PMS sync.
- No room upgrades or automatic room moves.
- No automatic commercial-inventory reconciliation from physical occupancy.
- No AI tool can assign rooms or perform operational transitions.
- Property-timezone policy automation and complex early/late rules are deferred.

The explicit Room, Stay, assignment, and event boundaries provide the seam for a later housekeeping/PMS integration without turning Booking or CRM into an operational source of truth.
