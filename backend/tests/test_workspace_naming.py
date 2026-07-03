"""Workspace naming strategy unit tests."""

import pytest

from app.services.workspace_naming import derive_workspace_naming


@pytest.mark.parametrize(
    ("email", "full_name", "display_name", "slug_base"),
    [
        ("alice@acme.com", "Alice", "Acme Workspace", "acme"),
        ("bob@acme.co.uk", None, "Acme Workspace", "acme"),
        ("dev@nimble-labs.io", "Dev", "Nimble Labs Workspace", "nimble-labs"),
    ],
)
def test_company_naming_has_independent_slug_base(
    email, full_name, display_name, slug_base
) -> None:
    naming = derive_workspace_naming(email=email, full_name=full_name)
    assert naming.display_name == display_name
    assert naming.slug_base == slug_base


@pytest.mark.parametrize(
    ("email", "full_name", "display_name", "slug_base"),
    [
        (
            "alice@gmail.com",
            "Alice Example",
            "Alice Example's Workspace",
            "Alice Example",
        ),
        ("bob@yahoo.com", None, "bob's Workspace", "bob"),
    ],
)
def test_personal_email_falls_back_to_user_naming(
    email, full_name, display_name, slug_base
) -> None:
    naming = derive_workspace_naming(email=email, full_name=full_name)
    assert naming.display_name == display_name
    assert naming.slug_base == slug_base
