"""Tenant resolver foundation tests."""

import uuid

from starlette.datastructures import Headers

from app.core import context
from app.core.tenant import (
    TenantResolver,
    resolve_tenant,
    slug_from_host,
)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = Headers(headers)


def test_slug_from_host_extracts_subdomain() -> None:
    assert slug_from_host("acme.oneflow.ai", "oneflow.ai") == "acme"
    assert slug_from_host("acme.oneflow.ai:443", "oneflow.ai") == "acme"


def test_slug_from_host_ignores_root_and_reserved() -> None:
    assert slug_from_host("oneflow.ai", "oneflow.ai") is None
    assert slug_from_host("www.oneflow.ai", "oneflow.ai") is None
    assert slug_from_host("a.b.oneflow.ai", "oneflow.ai") is None
    assert slug_from_host("other.com", "oneflow.ai") is None


def test_header_id_takes_precedence() -> None:
    wid = uuid.uuid4()
    resolver = TenantResolver(base_domain="oneflow.ai")
    request = _FakeRequest(
        {"X-Workspace-Id": str(wid), "Host": "acme.oneflow.ai"}
    )
    tenant = resolver.resolve(request)
    assert tenant.workspace_id == wid
    assert tenant.source == "header"


def test_header_slug_resolution() -> None:
    resolver = TenantResolver(base_domain="oneflow.ai")
    tenant = resolver.resolve(_FakeRequest({"X-Workspace-Slug": "Acme"}))
    assert tenant.workspace_slug == "acme"
    assert tenant.source == "header"


def test_subdomain_resolution() -> None:
    resolver = TenantResolver(base_domain="oneflow.ai")
    tenant = resolver.resolve(_FakeRequest({"Host": "acme.oneflow.ai"}))
    assert tenant.workspace_slug == "acme"
    assert tenant.source == "subdomain"


def test_jwt_claim_resolution() -> None:
    resolver = TenantResolver(base_domain="oneflow.ai")
    tenant = resolver.resolve(
        _FakeRequest({}), jwt_payload={"workspace_slug": "acme"}
    )
    assert tenant.workspace_slug == "acme"
    assert tenant.source == "jwt"


def test_unresolved_when_no_signals() -> None:
    resolver = TenantResolver(base_domain="oneflow.ai")
    tenant = resolver.resolve(_FakeRequest({}))
    assert tenant.is_resolved is False
    assert tenant.source == "none"


def test_resolve_tenant_populates_log_context() -> None:
    resolve_tenant(_FakeRequest({"Host": "acme.oneflow.ai"}))
    assert context.get_log_context().get("workspace_id") == "acme"
    # Clean up contextvar for other tests.
    context.set_workspace_id(None)
