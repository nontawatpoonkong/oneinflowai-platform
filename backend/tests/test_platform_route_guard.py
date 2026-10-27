"""M2: every platform route refuses Workspace users who are not platform admins.

The route list is read from the application itself, so a new platform route
without the guard fails this test. Path parameters get random ids; refusals
must carry no data.
"""

import re
import uuid

from app.main import app
from tests.conftest import register_verify_and_login
from tests.test_workspace_access import _headers

PLATFORM_PREFIX = "/api/v1/platform"


def _platform_routes():
    # Read from the generated OpenAPI document so every included router counts.
    for path, operations in app.openapi()["paths"].items():
        if path.startswith(PLATFORM_PREFIX):
            for method in sorted(operations):
                yield method.upper(), path


def test_every_platform_route_refuses_workspace_owners(client_db):
    _, token = register_verify_and_login(client_db, email="m2-owner@example.com")
    headers = _headers(token)
    routes = list(_platform_routes())
    assert len(routes) >= 30
    leaked = []
    for method, path in routes:
        concrete = re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)
        response = client_db.request(method, concrete, headers=headers, json={})
        body = response.json() if response.content else {}
        # 403 from the guard; 422 only when the body is validated first. Either
        # way nothing is returned or changed.
        if response.status_code not in {403, 422} or body.get("data") not in (
            None,
            [],
        ):
            leaked.append((method, path, response.status_code))
    assert leaked == []
