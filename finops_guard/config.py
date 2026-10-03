"""Configuration — sensible defaults so the tool runs with zero setup.

A repo can drop a `.finops-guard.yml` to tune thresholds, required tags and the
fail policy. Everything is optional; omitted keys fall back to the defaults
below.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

try:
    import yaml  # PyYAML, optional
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class Config:
    # Governance
    required_tags: list[str] = field(default_factory=lambda: ["environment", "owner", "cost_center"])
    # A new monthly cost (GBP) at/above which a single resource needs sign-off / fails.
    warn_cost_gbp: float = 300.0
    fail_cost_gbp: float = 1500.0
    # A new untagged resource costing at/above this (GBP/mo) is a hard fail.
    fail_untagged_gbp: float = 300.0
    # Carbon nudges on/off.
    carbon_checks: bool = True
    # Flag non-prod compute to confirm an auto-shutdown schedule.
    nonprod_shutdown_check: bool = True
    # Fail policy: "fail" (only hard findings block) or "warn" (warnings block too).
    fail_on: str = "fail"
    # Pricing overrides.
    fx_usd_gbp: float | None = None

    @classmethod
    def load(cls, path: str | None) -> "Config":
        cfg = cls()
        if not path:
            return cfg
        if yaml is None:
            raise RuntimeError("PyYAML is required to read a config file; `pip install pyyaml`")
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for key, val in data.items():
            if hasattr(cfg, key) and val is not None:
                setattr(cfg, key, val)
        return cfg

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
