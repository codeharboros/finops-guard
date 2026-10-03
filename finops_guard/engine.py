"""Orchestration — plan in, verdict out.

`run_check` is the one entry point the CLI, the GitHub Action and any test call.
It parses, prices, evaluates and decides the verdict, returning a `CheckResult`
that the renderers turn into a PR comment or JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .plan import parse_plan, PlannedResource
from .pricebook import estimate, Estimate, FX_USD_GBP
import finops_guard.pricebook as _pricebook
from .rules import evaluate, GateFinding


@dataclass
class CheckResult:
    verdict: str                      # "pass" | "warn" | "fail"
    pairs: list[tuple[PlannedResource, Estimate]] = field(default_factory=list)
    findings: list[GateFinding] = field(default_factory=list)
    monthly_cost_gbp: float = 0.0     # net monthly delta (adds minus deletes)
    monthly_kgco2e: float = 0.0
    config: Config | None = None

    @property
    def annual_cost_gbp(self) -> float:
        return self.monthly_cost_gbp * 12

    @property
    def annual_kgco2e(self) -> float:
        return self.monthly_kgco2e * 12

    @property
    def n_fail(self) -> int:
        return sum(1 for f in self.findings if f.severity == "fail")

    @property
    def n_warn(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")

    @property
    def priced_resources(self) -> list[tuple[PlannedResource, Estimate]]:
        return [(r, e) for r, e in self.pairs if e.priced and r.adds_cost]

    @property
    def exit_code(self) -> int:
        if self.verdict == "fail":
            return 1
        if self.verdict == "warn" and self.config and self.config.fail_on == "warn":
            return 1
        return 0


def run_check(plan_json: dict, config: Config | None = None) -> CheckResult:
    config = config or Config()

    # Allow a per-engagement FX override without editing the pricebook module.
    if config.fx_usd_gbp:
        _pricebook.FX_USD_GBP = config.fx_usd_gbp

    resources = parse_plan(plan_json)
    pairs: list[tuple[PlannedResource, Estimate]] = [(r, estimate(r)) for r in resources]
    findings = evaluate(pairs, config)

    # Net cost/carbon delta: additions positive, deletions negative.
    monthly_cost = 0.0
    monthly_carbon = 0.0
    for r, e in pairs:
        if not e.priced:
            continue
        if r.action == "delete":
            monthly_cost -= e.monthly_cost_gbp
            monthly_carbon -= e.monthly_kgco2e
        elif r.adds_cost:
            monthly_cost += e.monthly_cost_gbp
            monthly_carbon += e.monthly_kgco2e

    verdict = "pass"
    if any(f.severity == "fail" for f in findings):
        verdict = "fail"
    elif any(f.severity == "warn" for f in findings):
        verdict = "warn"

    return CheckResult(
        verdict=verdict,
        pairs=pairs,
        findings=findings,
        monthly_cost_gbp=round(monthly_cost, 2),
        monthly_kgco2e=round(monthly_carbon, 1),
        config=config,
    )
