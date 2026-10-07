# Hotel Housekeeping and Room Readiness

Sprint 10.5 adds a focused housekeeping lifecycle without turning OneInFlow into a PMS.

## Separate authoritative concerns

`HotelRoom.operational_status` remains occupancy/operability: `AVAILABLE`, `OCCUPIED`, or `OUT_OF_SERVICE`. The independent `readiness_status` is `READY`, `DIRTY`, or `CLEANING`. A room is eligible for assignment and check-in only when it is active, operationally `AVAILABLE`, and `READY`.

Commercial RoomType daily inventory is unchanged. Housekeeping never adds, releases, or recalculates sellable inventory.

## Checkout and task lifecycle

Checkout atomically releases occupancy, changes the room to `AVAILABLE + DIRTY`, creates exactly one checkout housekeeping task per Stay/Room, and records immutable events. The task lifecycle is:

```text
PENDING -> IN_PROGRESS -> COMPLETED
   |            |
   +----------> CANCELLED
```

Starting requires a dirty room and changes readiness to `CLEANING`. Completion requires cleaning in progress, records the completion timestamp, and changes readiness to `READY`. Cancelling leaves or returns the room to `DIRTY`. Repeated start/completion/cancellation calls are deterministic. PostgreSQL row locks and a partial unique index enforce one active task per room.

## Assignment and authorization

The small `WorkspaceCapabilityService` makes operational permissions explicit without adding a database-backed RBAC system:

- `hotel.housekeeping.operate`: Owner, Admin, and Member. A Member can start or complete only a task assigned to that same user.
- `hotel.housekeeping.manage`: Owner and Admin. Required to assign or cancel tasks.
- `hotel.readiness.override`: Owner and Admin. Required for exceptional readiness correction.

All capabilities still require current membership in the same Workspace. Assignment is restricted to a member of that Workspace, and cross-Workspace resources remain invisible.

## Exceptional readiness override

`POST /api/v1/hotel/housekeeping/rooms/{room_id}/readiness-override` is the only direct readiness correction operation. It is not a generic room patch. The request requires a 10–500 character operational reason and accepts only `READY` or `DIRTY`; direct `CLEANING` overrides are rejected. An occupied room cannot be overridden.

Every accepted override atomically records an immutable `hotel_room_readiness_override_events` row containing Workspace, property, room, actor, timestamp, reason, and previous/new readiness. A `READY` correction cancels any active housekeeping task, while a `DIRTY` correction creates a single pending task when none exists. The existing active-task uniqueness constraint remains authoritative under concurrency.

## Out of service

Moving an unoccupied room to `OUT_OF_SERVICE` preserves readiness and any housekeeping task. Cleaning may finish while the room remains out of service, but completion does not return it to operational availability. The existing explicit return-to-service operation changes only occupancy/operability and never silently changes readiness.

## API and UI

Workspace-scoped routes under `/api/v1/hotel/housekeeping` provide bounded task listing/detail plus explicit assign, start, complete, cancel, and readiness-override operations. The dashboard Housekeeping page shows real room, property, readiness, task, assignee, priority, checkout, and start information. Rooms display occupancy and readiness separately.

Operational pages use the paginated API response rather than loading every record. Housekeeping, Rooms, Stays, and Guests provide previous/next controls, page-size selection, totals, and retain active filters while paging. Supported filters are:

- Housekeeping: property, task status, assignee, priority, and room readiness.
- Rooms: property, room type, occupancy/operational status, readiness, and active state.
- Stays: property, lifecycle state (`EXPECTED`, `CHECKED_IN`, `CHECKED_OUT`, `NO_SHOW`), exact planned arrival date, and exact planned departure date. Planned dates are property-local business dates; the UI does not derive a browser-timezone "today" value.
- Guests: search, payment-exception, and repeat-guest filters.

The Booking API currently returns a bounded non-paginated list, so this hardening sprint does not add a fake client-side Booking paginator.

## Migration behavior

The Sprint 10.5 migration gave existing rooms deterministic `READY` readiness. Sprint 10.5.1 adds only the immutable override-audit table; it does not rewrite room state. For an occupied room, stored readiness remains its last known housekeeping condition, not arrival eligibility: occupancy still blocks assignment/check-in, and checkout always changes it to `DIRTY`. Out-of-service rooms remain out of service and are not automatically made operational.

## Audit, CRM, AI, and PMS seam

Housekeeping and readiness-override events contain task or room scope, Workspace, actor, timestamps, and safe operational metadata only. Tasks are not Customer 360 data and staff housekeeping details are not exposed as customer information. AI has no writable housekeeping or readiness-override tools.

A future PMS adapter must explicitly map provider room state to OneInFlow occupancy and readiness; identical external status vocabularies are not assumed.

## Deferred

Maintenance tickets, linen/stock, minibar, staff scheduling, payroll, optimization AI, predictive duration, room upgrades, key cards, OTA/PMS synchronization, and generic workflows remain out of scope.
