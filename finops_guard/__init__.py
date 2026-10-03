"""finops-guard — shift-left cost, carbon and governance checks for Terraform.

Point it at a `terraform show -json` plan and it tells you, *before* you merge,
what the change will cost per month, how much carbon it will emit, and whether
it breaks your tagging / budget / region guardrails — as a PR comment that can
fail CI.

The design mirrors the audit engine: everything a provider emits is normalized
to one shape (`PlannedResource`), so every rule works across Azure, AWS and
Databricks without knowing which cloud it came from. Add a provider by adding a
pricebook entry, not by rewriting rules.

Estimates are transparent list-price approximations, deliberately conservative,
and always labelled as estimates — never presented as a bill.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .engine import run_check, CheckResult  # noqa: E402,F401
from .plan import PlannedResource, parse_plan  # noqa: E402,F401
from .config import Config  # noqa: E402,F401

__all__ = ["run_check", "CheckResult", "PlannedResource", "parse_plan", "Config", "__version__"]
