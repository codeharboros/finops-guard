# finops-guard

**See what a Terraform change will cost — in money and carbon — before you merge it.**

`finops-guard` reads a Terraform plan and posts a comment on the pull request:
the monthly and annual cost delta, the carbon delta, and any governance issues
(missing tags, un-owned spend, oversized resources, dirty-grid regions). It can
fail the check, so cost and carbon become a merge gate like tests or linting —
not a surprise on next month's bill.

It is **cross-vendor by design**: Azure, AWS and Databricks resources are
normalized to one shape, so a single gate covers a plan that spans clouds. Most
cost tools look *backwards* at one platform's bill; this looks *forwards* across
all of them, in the pull request.

```
🟥 finops-guard — cost & carbon gate: FAIL

This change adds about £3,969/mo (£47,622/yr) and 192 kgCO2e/mo.

❌ Must fix (2)
- Large new monthly cost — azurerm_linux_virtual_machine.ml_trainer
  Adds about £1,765/mo. Above the £1,500 hard limit — needs explicit sign-off.
- New spend with no owner / cost-centre tag — aws_db_instance.analytics
  Adds about £394/mo but cannot be attributed. Missing: environment, owner, cost_center.
```

## Quickstart (60 seconds)

```bash
pip install finops-guard            # or: pip install -e ".[yaml]" from this repo

terraform plan -out tfplan
terraform show -json tfplan > plan.json

finops-guard check plan.json        # prints the comment; exit 1 if the gate fails
```

No config needed to start. Drop a `.finops-guard.yml` when you want to tune
thresholds, required tags, or the fail policy.

## What it checks

| Check | Severity | What it catches |
| --- | --- | --- |
| **Cost delta** | info | Monthly + annual £ a change adds (or removes), per resource and in total |
| **Carbon delta** | info | kgCO2e/mo from the new compute, by region grid intensity |
| **Large new cost** | warn / **fail** | A single resource over your review / hard-limit thresholds |
| **Un-owned spend** | **fail** | Costly resources with no owner / cost-centre tag — unattributable spend |
| **Missing required tags** | warn | Any required tag absent from a new resource |
| **Non-prod always-on** | warn | Non-prod compute with no auto-shutdown schedule |
| **Cleaner region** | warn | Dirty-grid deployments where a much cleaner region exists |
| **Unpriced resource** | note | Resource types not yet in the pricebook (so coverage is honest) |

Hard findings (`fail`) block the merge. Warnings are advisory unless you set
`fail_on: warn`.

## As a CI gate (GitHub Actions)

```yaml
# .github/workflows/finops-guard.yml
name: finops-guard
on:
  pull_request:
    paths: ["**/*.tf", "**/*.tfvars"]
permissions:
  contents: read
  pull-requests: write
jobs:
  cost-carbon-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with: { terraform_wrapper: false }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: |
          terraform init -input=false
          terraform plan -out=tfplan -input=false
          terraform show -json tfplan > plan.json
      - uses: AkshaySoooryavanshi/finops-guard@v0
        with:
          plan: plan.json
          fail-on: fail
```

The plan is **read-only** — no write credentials are required to run the gate.
See [`examples/workflow.yml`](examples/workflow.yml) and [`action.yml`](action.yml).

## Configuration

```yaml
# .finops-guard.yml
required_tags: [environment, owner, cost_center]
warn_cost_gbp: 300        # review above this (£/mo per resource)
fail_cost_gbp: 1500       # hard-fail above this
fail_untagged_gbp: 300    # hard-fail un-owned spend above this
carbon_checks: true
nonprod_shutdown_check: true
fail_on: fail             # or "warn" to block on warnings too
# fx_usd_gbp: 0.79        # per-engagement FX override
```

## How the numbers are built

Estimates are **public list-price approximations, deliberately conservative,
and always labelled as estimates** — a forecast to steer a decision, never a
bill. Cost is `hourly list price × 730 × FX`. Carbon is modelled from vCPU power
draw (`watts/vCPU × hours × PUE`) times the region's grid intensity in
gCO2e/kWh. Every figure in a comment carries its basis. Add a SKU or a region by
adding a row to [`finops_guard/pricebook.py`](finops_guard/pricebook.py) — no
rule changes.

Coverage today: Azure VMs/AKS/ACR/storage, AWS EC2/RDS/S3, Databricks
clusters/jobs/SQL warehouses. Anything else is listed as *unpriced* rather than
silently ignored.

## Why this exists

It's the open, in-the-PR front end of a broader cross-vendor FinOps practice —
cost, carbon and governance in one data model. The audit and guardrail work that
sits behind it is a separate, commercial engagement. This part is open source
because the best place to stop waste is before it is provisioned, and that
belongs in everyone's pipeline.

## License

Apache-2.0.
