"""Tenant (workspace) resolution foundation.

Extracts the *current workspace context* for multi-tenant services from the
incoming request and/or a decoded JWT payload. This is foundation only: it is
not wired into any existing endpoint, so no API contract changes.

Resolution order (first match wins):
  1. ``X-Workspace-Id`` header   (explicit UUID)
  2. ``X-Workspace-Slug`` header (explicit canonical slug)
  3. Subdomain                   (acme.oneflow.ai -> "acme")
  4. JWT claim                   (``workspace_id`` / ``workspace_slug``)

Slug is the canonical identifier; a UUID is resolved to a concrete workspace
by services in a later sprint. The resolver itself performs no DB access.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.core import context
from app.core.config import get_settings

settings = get_settings()

WORKSPACE_ID_HEADER = "X-Workspace-Id"
WORKSPACE_SLUG_HEADER = "X-Workspace-Slug"

# Subdomains that never denote a workspace tenant.
_NON_TENANT_SUBDOMAINS = frozenset({"www", "api", "app", "admin"})


class _HasHeaders(Protocol):
    @property
    def headers(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class TenantContext:
    workspace_id: uuid.UUID | None = None
    workspace_slug: str | None = None
    source: str = "none"  # header | subdomain | jwt | none

    @property
    def is_resolved(self) -> bool:
        return self.workspace_id is not None or self.workspace_slug is not None

    @property
    def identifier(self) -> str | None:
        if self.workspace_id is not None:
            return str(self.workspace_id)
        return self.workspace_slug


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def slug_from_host(host: str, base_domain: str) -> str | None:
    """Extract a single-label workspace slug from a Host header."""
    if not host or not base_domain:
        return None
    host = host.split(":", 1)[0].strip().strip(".").lower()
    suffix = f".{base_domain.lower()}"
    if not host.endswith(suffix):
        return None
    sub = host[: -len(suffix)]
    # Only a single left-most label is treated as the tenant slug.
    if not sub or "." in sub or sub in _NON_TENANT_SUBDOMAINS:
        return None
    return sub


class TenantResolver:
    def __init__(self, base_domain: str | None = None) -> None:
        self.base_domain = base_domain or settings.BASE_DOMAIN

    def resolve(
        self, request: _HasHeaders, jwt_payload: dict[str, Any] | None = None
    ) -> TenantContext:
        headers = request.headers

        header_id = _parse_uuid(headers.get(WORKSPACE_ID_HEADER))
        if header_id is not None:
            return TenantContext(workspace_id=header_id, source="header")

        header_slug = headers.get(WORKSPACE_SLUG_HEADER)
        if header_slug:
            return TenantContext(workspace_slug=header_slug.lower(), source="header")

        sub = slug_from_host(headers.get("host", ""), self.base_domain)
        if sub:
            return TenantContext(workspace_slug=sub, source="subdomain")

        if jwt_payload:
            claim_id = _parse_uuid(jwt_payload.get("workspace_id"))
            if claim_id is not None:
                return TenantContext(workspace_id=claim_id, source="jwt")
            claim_slug = jwt_payload.get("workspace_slug")
            if claim_slug:
                return TenantContext(
                    workspace_slug=str(claim_slug).lower(), source="jwt"
                )

        return TenantContext()


_resolver = TenantResolver()


def resolve_tenant(
    request: _HasHeaders, jwt_payload: dict[str, Any] | None = None
) -> TenantContext:
    """Resolve tenant context and populate the logging context (if any)."""
    tenant = _resolver.resolve(request, jwt_payload)
    if tenant.identifier is not None:
        context.set_workspace_id(tenant.identifier)
    return tenant
