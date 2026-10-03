"""Gate rules — the shift-left equivalent of the audit's waste/governance rules.

Each rule looks at the *planned* resources and their estimates and emits
`GateFinding`s. Severity drives the verdict: any `fail` blocks the merge (exit
1); `warn` is advisory unless the repo sets `fail_on: warn`; `info` never blocks.

Rules are intentionally explainable — each finding says what it found, what it
will cost or emit, and what to do about it. No black-box scoring.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .pricebook import Estimate, cleaner_region, REGION_INTENSITY


@dataclass
class GateFinding:
    severity: str        # "fail" | "warn" | "info"
    code: str            # stable machine code, e.g. "missing_required_tag"
    title: str
    resource: str        # resource address
    detail: str
    monthly_gbp: float = 0.0
    monthly_kgco2e: float = 0.0
    suggestion: str = ""


_SEV_ORDER = {"fail": 0, "warn": 1, "info": 2}


def evaluate(pairs: list[tuple], config: Config) -> list[GateFinding]:
    """pairs: list of (PlannedResource, Estimate). Returns findings, worst first."""
    findings: list[GateFinding] = []

    for res, est in pairs:
        if res.action == "delete":
            continue
        _check_tags(res, est, config, findings)
        _check_cost(res, est, config, findings)
        _check_nonprod_shutdown(res, est, config, findings)
        if config.carbon_checks:
            _check_carbon_region(res, est, findings)
        if not est.priced and res.adds_cost:
            findings.append(GateFinding(
                "info", "unpriced_resource",
                "No price model for this resource type",
                res.address,
                f"{res.resource_type} has no estimate yet — cost/carbon not counted. "
                "Add it to the pricebook to include it.",
            ))

    findings.sort(key=lambda f: (_SEV_ORDER.get(f.severity, 9), -f.monthly_gbp))
    return findings


def _check_tags(res, est: Estimate, config: Config, out: list[GateFinding]) -> None:
    if not res.adds_cost or not res.is_new:
        return
    present = {k.lower() for k in res.tags}
    missing = [t for t in config.required_tags if t.lower() not in present]
    if not missing:
        return
    untagged_owner = not res.has_owner_tag()
    # A costly, owner-less new resource is a hard fail — it cannot be attributed.
    if untagged_owner and est.monthly_cost_gbp >= config.fail_untagged_gbp:
        out.append(GateFinding(
            "fail", "untagged_spend",
            "New spend with no owner / cost-centre tag",
            res.address,
            f"Adds about £{est.monthly_cost_gbp:,.0f}/mo but carries no owner or cost-centre "
            f"tag, so it cannot be attributed. Missing: {', '.join(missing)}.",
            monthly_gbp=est.monthly_cost_gbp,
            suggestion="Add owner / cost_center tags before merge.",
        ))
    else:
        out.append(GateFinding(
            "warn", "missing_required_tag",
            "Missing required tag(s)",
            res.address,
            f"Missing required tag(s): {', '.join(missing)}.",
            monthly_gbp=est.monthly_cost_gbp,
            suggestion=f"Add {', '.join(missing)} to this resource.",
        ))


def _check_cost(res, est: Estimate, config: Config, out: list[GateFinding]) -> None:
    if not res.adds_cost or est.monthly_cost_gbp <= 0:
        return
    c = est.monthly_cost_gbp
    if c >= config.fail_cost_gbp:
        out.append(GateFinding(
            "fail", "expensive_resource",
            "Large new monthly cost",
            res.address,
            f"Adds about £{c:,.0f}/mo (£{c*12:,.0f}/yr). Above the £{config.fail_cost_gbp:,.0f} "
            f"hard limit — needs explicit sign-off. Basis: {est.basis}.",
            monthly_gbp=c,
            suggestion="Confirm the size is intended, or add an approved-cost label to override.",
        ))
    elif c >= config.warn_cost_gbp:
        out.append(GateFinding(
            "warn", "notable_cost",
            "Notable new monthly cost",
            res.address,
            f"Adds about £{c:,.0f}/mo (£{c*12:,.0f}/yr). Basis: {est.basis}.",
            monthly_gbp=c,
            suggestion="Check the SKU is right-sized for the workload.",
        ))


def _check_nonprod_shutdown(res, est: Estimate, config: Config, out: list[GateFinding]) -> None:
    if not config.nonprod_shutdown_check or not res.adds_cost:
        return
    # Databricks run-rate already assumes ~160 active hrs/mo (auto-termination),
    # so the always-on flag only applies to VM / AKS / EC2-style compute.
    if res.provider == "databricks":
        return
    if res.environment == "nonprod" and est.vcpu > 0 and est.monthly_cost_gbp > 0:
        # A plan can't prove a shutdown schedule exists; flag to confirm.
        potential = round(est.monthly_cost_gbp * (730 - 45) / 730)
        out.append(GateFinding(
            "warn", "nonprod_always_on",
            "Non-prod compute — confirm auto-shutdown",
            res.address,
            f"Non-prod compute at about £{est.monthly_cost_gbp:,.0f}/mo. If it runs 24x7, "
            f"an out-of-hours schedule would save roughly £{potential:,.0f}/mo.",
            monthly_gbp=est.monthly_cost_gbp,
            suggestion="Attach an auto-shutdown / start-stop schedule for non-prod.",
        ))


def _check_carbon_region(res, est: Estimate, out: list[GateFinding]) -> None:
    if not res.adds_cost or est.monthly_kgco2e <= 1:
        return
    alt = cleaner_region(res.provider, res.region)
    if not alt:
        return
    alt_region, alt_intensity = alt
    current = REGION_INTENSITY.get(res.region)
    if current is None:
        return
    saved = round(est.monthly_kgco2e * (1 - alt_intensity / current), 1)
    out.append(GateFinding(
        "warn", "high_carbon_region",
        "Cleaner region available",
        res.address,
        f"About {est.monthly_kgco2e:,.0f} kgCO2e/mo in {res.region} "
        f"({current:.0f} g/kWh). {alt_region} is {alt_intensity:.0f} g/kWh.",
        monthly_kgco2e=est.monthly_kgco2e,
        suggestion=f"If latency/residency allow, {alt_region} would cut about {saved:,.0f} kgCO2e/mo.",
    ))
