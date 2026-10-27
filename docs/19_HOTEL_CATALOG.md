# Hotel Catalog and Trusted Availability

Sprint 10.0 introduces the first Hotel vertical boundary without adding Hotel
fields to Platform Core records. `Property`, `RoomType`, `RatePlan`, and
`InventoryDate` are Workspace-owned PostgreSQL records and are authoritative
for identity, occupancy, base price, and daily availability.

Knowledge and Qdrant may continue to describe facilities and policies, but they
must not determine price, capacity, inventory, or availability.

## Deterministic availability

A stay uses the half-open date interval `[check_in, check_out)`. Every night
must have an inventory row. Daily availability is:

```text
total_units - reserved_units - blocked_units
```

The availability for the complete stay is the minimum daily value. A missing
or sold-out day excludes the room type. Inactive properties, room types, and
rate plans are excluded, and requested adult/child/total occupancy must fit the
structured room limits.

## Quote semantics

Sprint 10.0 has no dynamic pricing, taxes, fees, discounts, or promotions. Each
night uses the active rate plan's `base_price`; the returned `subtotal` is the
Decimal sum of those nightly rates. It is not advertised as a tax-inclusive or
final payable amount.

## Tool boundary

`SearchAvailabilityTool` is a typed, read-only adapter over
`HotelAvailabilityService`. It cannot mutate inventory, create a Booking, or
change Payment state. The existing ActionDefinition/ActionRequest flow remains
a manual fulfillment and confirmation queue and is deliberately not reused as
a synchronous query mechanism.

## Future Booking consistency

There is no Booking or hold in Sprint 10.0. `reserved_units` is explicitly
managed by an owner/admin. A future Booking sprint must reserve inventory in a
single PostgreSQL transaction using row locks or an atomic conditional update,
for example updating a stay's daily rows only when every row has sufficient
remaining capacity. Booking idempotency and an immutable transition/event
record must be part of that transaction; AI must never update inventory
directly.
