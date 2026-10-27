Primary

Cyan

Accent

Blue

Background

Black

White

Radius

16px

Animation

Subtle

Glass

Yes

Blur

Yes

Dashboard Rule
    Owner Dashboard

Sprint 9.1 Operations Rule
    Primary navigation: Overview, Inbox, Actions, Knowledge, Payments,
    Channels, Notifications, Workspace / Settings.
    Every data surface provides loading, safe error/retry, and empty states.
    Operational status labels reflect persisted backend states; do not display
    delivered/read channel receipts that the platform does not persist.
    Owner/admin-only configuration controls are role-aware, but backend
    authorization remains authoritative.
    Desktop tables must remain horizontally usable and core workflows must
    collapse without losing access on narrow screens.
    Analytics is a first-class permission-aware operational surface. It uses
    real source data, explicit unsupported states, bounded date controls, and
    labeled Cyan/Pink charts that remain readable in light/dark mode.

Audit and Usage Rule
    Settings → Audit Log is a dense administrative history with actor, action,
    area, resource, result, filters, pagination, and a safe-metadata drawer.
    Product usage tracks route-level page views only. Never add keystrokes,
    form capture, session replay, productivity rankings, or employee scores.

Workspace Onboarding Rule
    Registration does not create a Workspace. An authenticated user with no
    memberships sees Create Workspace or Join a hotel team. Join-code resolution
    shows only the Workspace name, then creates a pending request for review;
    the operational dashboard remains unavailable until membership exists.

Knowledge Configuration Rule
    Keep Knowledge and AI Instructions as separate tabs. Knowledge supplies
    factual evidence and citations; AI Instructions configure tone and behavior
    and must never be presented as a developer console or evidence source.

    Never show

    CPU

    RAM

    Docker

    Redis

    Database

    Infrastructure

Platform Admin
    Can show

    CPU

    RAM

    Redis

    Docker

    Logs

    Health

## Rich Hotel catalog and calendar

Room Type create/edit uses separate Basic, Capacity, Beds, View, Amenities,
Photos, and Physical Rooms sections. Amenities use grouped labels and typed
controls; photos require alt text. The availability grid keeps a sticky Room
Type column on desktop and uses a horizontal date strip on mobile. Its
green/yellow/orange/red utilization scale is operational semantics, not brand
color, and every cell also displays used/total numbers.

## Promotion administration

Workspace Promotions uses dense Campaigns, Codes, and Usage tabs rather than
coupon-game visuals. Forms separate identity, discount, validity, eligibility,
and limits. Cyan remains the primary action color and pink is restrained to
supporting emphasis. Member controls are read-only unless `promotion.manage`
is granted, and backend authorization remains authoritative. Monetary summaries
must label currency and never visually combine unlike currencies.

## Platform Console

`/platform` uses a distinct dense desktop-first shell labelled “OneInFlowAI
Platform” with Overview, Users, Workspaces, Subscriptions, Marketing,
Analytics, Operations, Audit, and System navigation. Cyan is the primary
operational accent and pink is reserved for attention/high-impact boundaries.
Tables remain horizontally usable on tablet, status always includes text, and
browser/dialog confirmation plus a required reason precedes high-impact
actions. Hotel Workspace navigation and customer PII are not duplicated into
this shell.
