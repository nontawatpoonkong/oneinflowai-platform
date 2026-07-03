"""Workspace naming strategy.

Produces two independent values at registration time:
  - ``display_name``: human-facing label (e.g. "Acme Workspace");
  - ``slug_base``: the seed for the canonical, URL/subdomain-safe slug
    (e.g. "acme"), generated independently of the display name.

Slug is the canonical workspace identifier (supports oneflow.ai/acme and
acme.oneflow.ai); the display name is presentational only. This does not
change any API contract — only the generated values.
"""

import re
from dataclasses import dataclass

# Common personal/free email providers -> treat as "no company".
_PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "hey.com",
    }
)

# Second-level labels that are not the company (e.g. acme.co.uk -> "acme").
_REGISTRY_LABELS = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})

_WORD_SPLIT = re.compile(r"[-_]+")


@dataclass(frozen=True, slots=True)
class WorkspaceNaming:
    display_name: str
    slug_base: str


def _company_label_from_domain(domain: str) -> str | None:
    domain = domain.strip().lower()
    if not domain or domain in _PERSONAL_EMAIL_DOMAINS:
        return None

    parts = [p for p in domain.split(".") if p]
    if len(parts) < 2:
        return None

    label = parts[-2]
    if label in _REGISTRY_LABELS and len(parts) >= 3:
        label = parts[-3]
    return label or None


def _prettify(label: str) -> str:
    words = [w for w in _WORD_SPLIT.split(label) if w]
    return " ".join(word.capitalize() for word in words) or label.capitalize()


def derive_workspace_naming(*, email: str, full_name: str | None) -> WorkspaceNaming:
    """Return the display name and (independent) slug base for a new workspace."""
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    label = _company_label_from_domain(domain)
    if label:
        # Company-oriented: display "Acme Workspace", slug base "acme".
        return WorkspaceNaming(
            display_name=f"{_prettify(label)} Workspace",
            slug_base=label,
        )

    # Backward-compatible fallback for personal / unknown-domain emails.
    if full_name and full_name.strip():
        base = full_name.strip()
    elif email and "@" in email:
        base = email.split("@")[0]
    else:
        base = "My"
    return WorkspaceNaming(display_name=f"{base}'s Workspace", slug_base=base)
