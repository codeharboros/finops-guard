"""Renderers — turn a CheckResult into a PR comment (Markdown) or JSON.

The Markdown is written to read well as a GitHub PR comment: a one-line verdict
a reviewer sees at a glance, the cost/carbon delta, what must be fixed, and a
collapsed table of everything priced. JSON is for machines (dashboards, the
audit pipeline, tests).
"""
from __future__ import annotations

import json
from dataclasses import asdict

from .engine import CheckResult

_BADGE = {
    "pass": ("🟩", "PASS"),
    "warn": ("🟨", "WARN"),
    "fail": ("🟥", "FAIL"),
}
_SEV_HEAD = {
    "fail": "❌ Must fix",
    "warn": "⚠️ Review",
    "info": "ℹ️ Note",
}

# A petrol car emits roughly 0.17 kgCO2e per km — used only for a friendly scale.
_KG_PER_KM = 0.17


def _money(x: float) -> str:
    return f"£{x:,.0f}" if abs(x) >= 100 else f"£{x:,.2f}"


def render_markdown(result: CheckResult) -> str:
    emoji, label = _BADGE[result.verdict]
    L: list[str] = []
    L.append(f"## {emoji} finops-guard — cost & carbon gate: **{label}**")
    L.append("")

    # Headline delta
    mc, ac = result.monthly_cost_gbp, result.annual_cost_gbp
    mk, ak = result.monthly_kgco2e, result.annual_kgco2e
    verb = "adds" if mc >= 0 else "removes"
    L.append(f"This change **{verb} about {_money(abs(mc))}/mo** "
             f"({_money(abs(ac))}/yr) and **{abs(mk):,.0f} kgCO2e/mo**.")
    L.append("")
    L.append("| | Monthly | Annual |")
    L.append("| --- | --- | --- |")
    L.append(f"| 💷 Cost (net) | {_money(mc)} | {_money(ac)} |")
    km = abs(ak) / _KG_PER_KM
    L.append(f"| 🌍 Carbon | {mk:,.0f} kgCO2e | {ak:,.0f} kgCO2e (≈ {km:,.0f} km driven) |")
    L.append("")

    # Findings, grouped by severity (fail, warn, info)
    for sev in ("fail", "warn", "info"):
        group = [f for f in result.findings if f.severity == sev]
        if not group:
            continue
        L.append(f"### {_SEV_HEAD[sev]} ({len(group)})")
        for f in group:
            line = f"- **{f.title}** — `{f.resource}`  \n  {f.detail}"
            if f.suggestion:
                line += f"  \n  _→ {f.suggestion}_"
            L.append(line)
        L.append("")

    if result.verdict == "pass":
        L.append("No guardrail issues found. ✅")
        L.append("")

    # Collapsed resource table
    priced = result.priced_resources
    if priced:
        L.append("<details><summary>Priced resources "
                 f"({len(priced)})</summary>")
        L.append("")
        L.append("| Resource | Type | Region | £/mo | kgCO2e/mo |")
        L.append("| --- | --- | --- | ---: | ---: |")
        for r, e in sorted(priced, key=lambda p: -p[1].monthly_cost_gbp):
            L.append(f"| `{r.address}` | {r.resource_type} | {r.region} | "
                     f"{e.monthly_cost_gbp:,.0f} | {e.monthly_kgco2e:,.0f} |")
        L.append("")
        L.append("</details>")
        L.append("")

    unpriced = [(r, e) for r, e in result.pairs if not e.priced and r.adds_cost]
    if unpriced:
        names = ", ".join(sorted({r.resource_type for r, _ in unpriced}))
        L.append(f"<sub>Not yet priced (excluded from totals): {names}.</sub>")
        L.append("")

    L.append("<sub>Estimates from public list prices, deliberately conservative — "
             "a forecast, not a bill. Tune thresholds and required tags in "
             "`.finops-guard.yml`. — finops-guard</sub>")
    return "\n".join(L)


def render_json(result: CheckResult) -> str:
    payload = {
        "verdict": result.verdict,
        "exit_code": result.exit_code,
        "totals": {
            "monthly_cost_gbp": result.monthly_cost_gbp,
            "annual_cost_gbp": round(result.annual_cost_gbp, 2),
            "monthly_kgco2e": result.monthly_kgco2e,
            "annual_kgco2e": round(result.annual_kgco2e, 1),
        },
        "counts": {"fail": result.n_fail, "warn": result.n_warn,
                   "resources_priced": len(result.priced_resources)},
        "findings": [asdict(f) for f in result.findings],
        "resources": [
            {
                "address": r.address, "type": r.resource_type, "provider": r.provider,
                "action": r.action, "region": r.region, "environment": r.environment,
                "monthly_cost_gbp": e.monthly_cost_gbp, "monthly_kgco2e": e.monthly_kgco2e,
                "priced": e.priced, "basis": e.basis,
            }
            for r, e in result.pairs
        ],
    }
    return json.dumps(payload, indent=2)
