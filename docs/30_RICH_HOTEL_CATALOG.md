# Rich Hotel Catalog and Availability (Sprint 10.9C)

## Domain boundary

`RoomType` is the sellable room category. `HotelRoom` is a physical unit with
its own code, property, floor/building/wing, occupancy, readiness, active state,
and internal notes. Catalog metadata never replaces physical-room operations.

The active physical `HotelRoom` count is the only catalog quantity shown. No
manual disconnected quantity is persisted. Initial setup accepts exact room
codes only; the system does not generate ambiguous placeholder numbers.

## Guest-facing structured catalog

Room types support short and long descriptions, size, adult/child/total
capacity, smoking policy, accessibility, public highlights, and a controlled
view type with an optional custom label. Multiple normalized bed rows support
King, Queen, Double, Twin, Single, Bunk, Sofa Bed, Futon, and controlled custom
labels.

Amenities use a reusable registry grouped into bathroom, bedroom/furniture,
entertainment, food/drink, comfort, connectivity, safety, accessibility, and
other. Every definition declares BOOLEAN, NUMBER, or TEXT. Room assignments
must provide exactly the matching value type. Custom text is plain text only;
HTML is rejected. The initial catalog includes water heaters, hair dryers,
towels, TVs and numeric TV size, refrigerators, free water, kettles, snacks,
Wi-Fi, accessibility, safety, and the other catalog entries required by the
Pilot.

## Images and storage

Room types can have ordered image metadata and one cover image. Authorized
staff can reorder images and select the cover deterministically. Captions and
accessible alt text are bounded plain text. JPEG, PNG, and WebP signatures are
validated and binary data is stored through the existing `StorageProvider`.
PostgreSQL stores only storage keys, MIME type, ordering, cover state, and
display metadata.

The current repository has a safe local filesystem adapter suitable for local,
self-hosted, and Pilot validation. A production object-store/CDN adapter,
durable multi-instance shared volume, image resizing, and malware scanning are
not fabricated by this sprint and remain deployment requirements.

## Availability calendar

`GET /api/v1/hotel/availability-calendar` accepts a Workspace-scoped property,
start date, and a bounded range of 7, 14, or 30 days. The service performs batch
room-type and inventory queries rather than one query per cell.

For each existing `InventoryDate`:

- `used_units = reserved_units + blocked_units`
- `available_units = total_units - used_units`
- ratio is `used_units / total_units * 100`
- green: 0–39%, yellow: 40–69%, orange: 70–89%, red: 90–100%

Cells always show numeric used/total values; color is never the only signal.
Missing inventory fails closed with zero counts and `has_inventory=false`.
Detail UI shows total, reserved, blocked, available, and LOCAL/PMS authority.

PMS authority is displayed only from an active, explicitly mapped PMS
connection. No sync freshness is claimed when the backend has no freshness
contract.

## Authorization and AI

`room.read` controls catalog, physical room board, images, and availability.
`room.manage` controls room-type, bed, amenity, image, and physical-room
mutations. The existing capability registry remains authoritative.

The code-defined, read-only `get_room_catalog_facts` AI tool exposes only
guest-facing room fields, beds, amenities, image metadata, and active
physical-room count. It excludes physical-room internal notes and operational
details. This structured data is trusted Hotel evidence ahead of descriptive
Knowledge/RAG. It adds no AI mutation authority and does not change Booking,
Payment, Stay, Housekeeping, or PMS semantics.
