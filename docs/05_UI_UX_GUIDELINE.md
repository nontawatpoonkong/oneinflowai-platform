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
    Analytics remains a Sprint 9.4 placeholder, not an operational feature.

Workspace Onboarding Rule
    Registration does not create a Workspace. An authenticated user with no
    memberships sees Create Workspace and a truthful invitation-only Join state;
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
