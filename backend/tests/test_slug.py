"""Slug helper unit tests."""

from app.utils.slug import generate_unique_slug, slugify


def test_slugify_normalizes() -> None:
    assert slugify("Acme Corp") == "acme-corp"
    assert slugify("  Hello!!World  ") == "hello-world"
    assert slugify("###") == "workspace"  # empty -> fallback


async def test_generate_unique_slug_returns_base_when_free() -> None:
    async def never_exists(_slug: str) -> bool:
        return False

    assert await generate_unique_slug("My Team", never_exists) == "my-team"


async def test_generate_unique_slug_appends_suffix_on_collision() -> None:
    taken = {"acme"}

    async def exists(slug: str) -> bool:
        return slug in taken

    result = await generate_unique_slug("Acme", exists)
    assert result != "acme"
    assert result.startswith("acme-")


async def test_generate_unique_slug_avoids_reserved() -> None:
    async def never_exists(_slug: str) -> bool:
        return False

    # "api" is reserved (would clash with system subdomains), so it must not
    # be assigned even though the exists() check reports it free.
    result = await generate_unique_slug("API", never_exists)
    assert result != "api"
    assert result.startswith("api-")
