"""Parse a `terraform show -json <plan>` document into normalized resources.

The only thing the rest of the tool knows about Terraform lives here. A plan is
reduced to a flat list of `PlannedResource`, each tagged with the provider, the
action (create / update / delete / replace), the region, the tags and the raw
planned attributes. Everything downstream — pricing, carbon, rules — works off
that shape and never re-reads the plan JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Terraform resource-type prefix -> the provider bucket our pricebook uses.
_PROVIDER_PREFIX = {
    "azurerm_": "azure",
    "azuread_": "azure",
    "aws_": "aws",
    "databricks_": "databricks",
    "google_": "gcp",
}

# Attribute keys different providers use for "where it runs".
_REGION_KEYS = ("location", "region", "aws_region", "availability_zone")

# Tag keys that count as an owner / cost-centre for attribution.
_OWNER_TAG_KEYS = {"cost_center", "cost-centre", "costcentre", "owner", "team", "project"}
_ENV_TAG_KEYS = ("environment", "env", "stage", "tier")
_NONPROD_HINTS = ("nonprod", "non-prod", "dev", "develop", "staging", "stage", "test", "qa", "sandbox")


@dataclass
class PlannedResource:
    """One resource as the plan intends to leave it (the `after` state)."""

    address: str                       # e.g. "azurerm_linux_virtual_machine.api[0]"
    provider: str                      # azure | aws | databricks | gcp | other
    resource_type: str                 # e.g. "azurerm_linux_virtual_machine"
    name: str                          # the local name
    action: str                        # create | update | delete | replace | no-op | read
    region: str = "unknown"
    tags: dict[str, str] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)   # planned `after` attributes
    environment: str = "unknown"       # prod | nonprod | unknown (derived)

    @property
    def adds_cost(self) -> bool:
        # create and replace add the resource's full run-rate; update is treated
        # as steady-state (v1 does not diff sizes); delete/no-op/read add nothing.
        return self.action in ("create", "replace", "update")

    @property
    def is_new(self) -> bool:
        return self.action in ("create", "replace")

    def has_owner_tag(self) -> bool:
        keys = {k.lower() for k in self.tags}
        return bool(keys & _OWNER_TAG_KEYS)


def _bucket_provider(resource_type: str) -> str:
    for prefix, provider in _PROVIDER_PREFIX.items():
        if resource_type.startswith(prefix):
            return provider
    return "other"


def _derive_region(attrs: dict[str, Any]) -> str:
    for key in _REGION_KEYS:
        val = attrs.get(key)
        if isinstance(val, str) and val:
            return val.lower()
    return "unknown"


def _extract_tags(attrs: dict[str, Any]) -> dict[str, str]:
    # Azure/AWS use `tags`; some resources use `labels` or `tags_all`.
    for key in ("tags", "tags_all", "labels", "custom_tags"):
        val = attrs.get(key)
        if isinstance(val, dict) and val:
            return {str(k): str(v) for k, v in val.items() if v is not None}
    return {}


def _derive_environment(name: str, address: str, tags: dict[str, str]) -> str:
    # Prefer an explicit environment tag; fall back to naming hints.
    low_tags = {k.lower(): str(v).lower() for k, v in tags.items()}
    for key in _ENV_TAG_KEYS:
        if key in low_tags:
            v = low_tags[key]
            if any(h in v for h in _NONPROD_HINTS):
                return "nonprod"
            if "prod" in v:
                return "prod"
    hay = f"{name} {address}".lower()
    if any(h in hay for h in _NONPROD_HINTS):
        return "nonprod"
    if "prod" in hay:
        return "prod"
    return "unknown"


def parse_plan(plan_json: dict[str, Any]) -> list[PlannedResource]:
    """Turn a parsed `terraform show -json` plan into PlannedResource records.

    Reads `resource_changes[]`, using each change's `actions` and `after` state.
    Tolerant of missing fields so a partial or hand-written plan still parses.
    """
    out: list[PlannedResource] = []
    changes = plan_json.get("resource_changes") or []
    for rc in changes:
        if rc.get("mode") == "data":
            continue  # data sources cost nothing
        change = rc.get("change") or {}
        actions = change.get("actions") or ["no-op"]
        action = _normalize_action(actions)
        if action in ("no-op", "read", "delete"):
            # keep deletes out of v1 cost deltas but still record them for carbon credit later
            if action != "delete":
                continue
        # For a delete we value the `before` state (what is being removed);
        # otherwise the planned `after` state.
        if action == "delete":
            state = change.get("before") or {}
        else:
            state = change.get("after") or change.get("after_unknown") or {}
        if not isinstance(state, dict):
            state = {}
        after = state
        rtype = rc.get("type", "")
        tags = _extract_tags(after)
        name = rc.get("name", "")
        address = rc.get("address", f"{rtype}.{name}")
        out.append(
            PlannedResource(
                address=address,
                provider=_bucket_provider(rtype),
                resource_type=rtype,
                name=name,
                action=action,
                region=_derive_region(after),
                tags=tags,
                attrs=after,
                environment=_derive_environment(name, address, tags),
            )
        )
    return out


def _normalize_action(actions: list[str]) -> str:
    s = set(actions)
    if s == {"no-op"}:
        return "no-op"
    if s == {"read"}:
        return "read"
    if "create" in s and "delete" in s:
        return "replace"
    if s == {"create"}:
        return "create"
    if s == {"delete"}:
        return "delete"
    if s == {"update"}:
        return "update"
    # mixed / unknown -> treat as create so we never silently under-count cost
    return "create"
