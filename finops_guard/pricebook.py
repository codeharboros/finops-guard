"""Transparent cost + carbon estimates for planned resources.

Every number here is a published list-price approximation, chosen on the
conservative side and labelled as an estimate. The point is not pinpoint
accuracy — a bill is authoritative for that — but a *directionally correct,
explainable* figure the moment a resource appears in a plan, so the delta can
be seen before merge.

How a figure is built:
  monthly_cost = hourly_list_price x 730 hours x FX(USD->GBP)
  monthly_kwh  = power_kW x 730 hours x PUE
  monthly_kgCO2e = monthly_kwh x grid_intensity(region) / 1000

Power is modelled from vCPU count (a server draws roughly a fixed wattage per
active vCPU), with GPU SKUs given an explicit higher draw. Grid intensity is a
per-region operational figure in gCO2e/kWh.

Add a SKU or a region = add a row. No rule changes.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- global constants (override via config) -------------------------------- #
HOURS_PER_MONTH = 730
FX_USD_GBP = 0.79          # conservative; refresh per engagement
PUE = 1.2                  # typical hyperscale power-usage effectiveness
WATTS_PER_VCPU = 12.0      # approx active draw per vCPU for general compute
DEFAULT_INTENSITY = 400.0  # gCO2e/kWh — high, so unknown regions look worse, not better

# ---- grid carbon intensity, gCO2e/kWh (operational, approximate) ----------- #
# Lower is cleaner. Used both for the estimate and the "cleaner region" nudge.
REGION_INTENSITY: dict[str, float] = {
    # Azure
    "uksouth": 230, "ukwest": 230, "northeurope": 290, "westeurope": 330,
    "francecentral": 56, "swedencentral": 40, "norwayeast": 26,
    "germanywestcentral": 350, "switzerlandnorth": 45,
    "eastus": 370, "eastus2": 370, "westus2": 300, "centralus": 430,
    # AWS
    "eu-west-1": 290, "eu-west-2": 230, "eu-west-3": 56, "eu-central-1": 350,
    "eu-north-1": 40, "us-east-1": 370, "us-west-2": 300,
    # GCP (for completeness)
    "europe-west1": 110, "europe-west2": 230, "europe-north1": 40,
}

# A low-carbon alternative per provider, used to nudge (never auto-change).
_CLEAN_ALTERNATIVE = {
    "azure": ("swedencentral", 40.0),
    "aws": ("eu-north-1", 40.0),
    "gcp": ("europe-north1", 40.0),
}

# ---- SKU tables: name -> (vCPU, USD/hour list price) ----------------------- #
# Conservative pay-as-you-go Linux / on-demand list prices. Fallbacks are used
# when a size is unknown so an estimate is always produced.
_AZURE_VM: dict[str, tuple[int, float]] = {
    "standard_b2s": (2, 0.0416), "standard_b2ms": (2, 0.0832), "standard_b4ms": (4, 0.166),
    "standard_d2s_v5": (2, 0.096), "standard_d4s_v5": (4, 0.192), "standard_d8s_v5": (8, 0.384),
    "standard_d16s_v5": (16, 0.768), "standard_d2s_v3": (2, 0.096), "standard_d4s_v3": (4, 0.192),
    "standard_e4s_v5": (4, 0.252), "standard_e8s_v5": (8, 0.504), "standard_f8s_v2": (8, 0.338),
    "standard_nc6s_v3": (6, 3.06), "standard_nc24ads_a100_v4": (24, 3.67),
}
_AWS_EC2: dict[str, tuple[int, float]] = {
    "t3.small": (2, 0.0208), "t3.medium": (2, 0.0416), "t3.large": (2, 0.0832),
    "t3.xlarge": (4, 0.1664), "m5.large": (2, 0.096), "m5.xlarge": (4, 0.192),
    "m5.2xlarge": (8, 0.384), "m5.4xlarge": (16, 0.768), "c5.large": (2, 0.085),
    "c5.xlarge": (4, 0.17), "c5.2xlarge": (8, 0.34), "r5.large": (2, 0.126),
    "r5.xlarge": (4, 0.252), "p3.2xlarge": (8, 3.06), "g5.xlarge": (4, 1.006),
}
_AWS_RDS: dict[str, tuple[int, float]] = {
    "db.t3.medium": (2, 0.068), "db.t3.large": (2, 0.136), "db.m5.large": (2, 0.171),
    "db.m5.xlarge": (4, 0.342), "db.r5.large": (2, 0.24), "db.r5.xlarge": (4, 0.48),
}
# Databricks: all-in £-ish per hour per node (cloud VM + DBU at an engineering rate).
_DBX_NODE: dict[str, tuple[int, float]] = {
    "standard_ds3_v2": (4, 0.57), "standard_ds4_v2": (8, 1.13), "standard_ds5_v2": (16, 2.26),
    "standard_d4ds_v5": (4, 0.60), "standard_d8ds_v5": (8, 1.20),
    "m5.xlarge": (4, 0.55), "m5.2xlarge": (8, 1.10), "i3.xlarge": (4, 0.62),
}
# Databricks SQL warehouse size -> DBU/hour (serverless-ish), priced at _DBU_USD.
_DBX_SQL_SIZE: dict[str, float] = {
    "2x-small": 4, "x-small": 6, "small": 12, "medium": 24, "large": 40,
    "x-large": 80, "2x-large": 144, "3x-large": 272, "4x-large": 528,
}
_DBU_USD = 0.55  # premium SQL DBU list price, USD

# Flat monthly list prices for non-compute resources (USD/month), carbon ~0.
_AZURE_ACR = {"basic": 5, "standard": 20, "premium": 50}
_STORAGE_FLAT_USD = 25     # a nominal placeholder for a storage account's base
_LB_FLAT_USD = 18          # load balancer / app gateway base


@dataclass
class Estimate:
    monthly_cost_gbp: float
    monthly_kgco2e: float
    basis: str                 # human-readable explanation of how it was derived
    priced: bool = True        # False => we could not price it (shown as "unpriced")
    vcpu: int = 0


def _carbon(vcpu: int, region: str, *, gpu_kw: float = 0.0) -> float:
    """Monthly kgCO2e from vCPU-derived (or explicit GPU) power and region grid."""
    kw = gpu_kw if gpu_kw else (vcpu * WATTS_PER_VCPU / 1000.0)
    monthly_kwh = kw * HOURS_PER_MONTH * PUE
    intensity = REGION_INTENSITY.get(region, DEFAULT_INTENSITY)
    return round(monthly_kwh * intensity / 1000.0, 1)


def _cost_from_hourly(usd_per_hour: float) -> float:
    return round(usd_per_hour * HOURS_PER_MONTH * FX_USD_GBP, 2)


def cleaner_region(provider: str, region: str) -> tuple[str, float] | None:
    """Return (region, intensity) of a materially cleaner same-provider region.

    Returns None if the current region is already clean or unknown.
    """
    current = REGION_INTENSITY.get(region)
    alt = _CLEAN_ALTERNATIVE.get(provider)
    if current is None or alt is None:
        return None
    alt_region, alt_intensity = alt
    # Only nudge for a genuinely dirty region (>= 250 g/kWh) where the move saves
    # a lot (>= 150 g/kWh) — so clean regions like UK/Nordic are never nagged.
    if alt_region != region and current >= 250 and (current - alt_intensity) >= 150:
        return alt
    return None


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def estimate(res) -> Estimate:
    """Cost + carbon for one PlannedResource. Always returns an Estimate."""
    rt = res.resource_type
    a = res.attrs
    region = res.region

    # ---- Azure VMs -------------------------------------------------------- #
    if rt in ("azurerm_linux_virtual_machine", "azurerm_windows_virtual_machine"):
        size = str(a.get("size") or a.get("vm_size") or "").lower()
        vcpu, hourly = _AZURE_VM.get(size, (4, 0.20))
        gpu_kw = 0.30 if "nc" in size or "a100" in size else 0.0
        return Estimate(_cost_from_hourly(hourly), _carbon(vcpu, region, gpu_kw=gpu_kw),
                        f"Azure VM {size or '(unknown size)'}: {vcpu} vCPU @ ${hourly}/hr list", vcpu=vcpu)

    if rt == "azurerm_kubernetes_cluster":
        pool = (a.get("default_node_pool") or [{}])
        pool = pool[0] if isinstance(pool, list) and pool else (pool if isinstance(pool, dict) else {})
        size = str(pool.get("vm_size") or "").lower()
        count = _int(pool.get("node_count"), 3)
        vcpu, hourly = _AZURE_VM.get(size, (4, 0.20))
        return Estimate(_cost_from_hourly(hourly * count), _carbon(vcpu * count, region),
                        f"AKS default pool: {count} x {size or '(unknown)'} ({vcpu} vCPU each)", vcpu=vcpu * count)

    if rt == "azurerm_container_registry":
        sku = str(a.get("sku") or "basic").lower()
        usd = _AZURE_ACR.get(sku, 20)
        return Estimate(round(usd * FX_USD_GBP, 2), 0.0, f"ACR {sku} tier base", vcpu=0)

    # ---- AWS -------------------------------------------------------------- #
    if rt == "aws_instance":
        itype = str(a.get("instance_type") or "").lower()
        vcpu, hourly = _AWS_EC2.get(itype, (4, 0.19))
        gpu_kw = 0.30 if itype.startswith(("p3", "p4", "g5", "g4")) else 0.0
        return Estimate(_cost_from_hourly(hourly), _carbon(vcpu, region, gpu_kw=gpu_kw),
                        f"EC2 {itype or '(unknown)'}: {vcpu} vCPU @ ${hourly}/hr list", vcpu=vcpu)

    if rt == "aws_db_instance":
        cls = str(a.get("instance_class") or "").lower()
        vcpu, hourly = _AWS_RDS.get(cls, (2, 0.17))
        multi = bool(a.get("multi_az"))
        factor = 2 if multi else 1
        return Estimate(_cost_from_hourly(hourly * factor), _carbon(vcpu * factor, region),
                        f"RDS {cls or '(unknown)'}{' multi-AZ' if multi else ''}: {vcpu} vCPU", vcpu=vcpu * factor)

    if rt in ("aws_lb", "aws_alb", "azurerm_lb", "azurerm_application_gateway"):
        return Estimate(round(_LB_FLAT_USD * FX_USD_GBP, 2), 0.0, "Load balancer base charge", vcpu=0)

    # ---- Databricks ------------------------------------------------------- #
    if rt in ("databricks_cluster", "databricks_job"):
        node = str(a.get("node_type_id") or "").lower()
        workers = _int(a.get("num_workers"), 2)
        vcpu, hourly = _DBX_NODE.get(node, (4, 0.60))
        nodes = workers + 1  # + driver
        # Databricks clusters are rarely 24x7; assume 160 active hours/month unless prod.
        active_hours = 160 if res.environment != "prod" else HOURS_PER_MONTH
        cost = round(hourly * active_hours * nodes * FX_USD_GBP, 2)
        kw = vcpu * nodes * WATTS_PER_VCPU / 1000.0
        carbon = round(kw * active_hours * PUE * REGION_INTENSITY.get(region, DEFAULT_INTENSITY) / 1000.0, 1)
        return Estimate(cost, carbon,
                        f"Databricks {nodes} x {node or '(unknown)'} @ ~{active_hours} hrs/mo", vcpu=vcpu * nodes)

    if rt in ("databricks_sql_endpoint", "databricks_sql_warehouse"):
        size = str(a.get("cluster_size") or a.get("size") or "small").lower()
        dbu = _DBX_SQL_SIZE.get(size, 12)
        active_hours = 160
        cost = round(dbu * _DBU_USD * active_hours * FX_USD_GBP, 2)
        # SQL warehouse carbon approximated from DBU as a compute proxy.
        carbon = round((dbu * 0.05) * active_hours * PUE * REGION_INTENSITY.get(region, DEFAULT_INTENSITY) / 1000.0, 1)
        return Estimate(cost, carbon, f"Databricks SQL {size}: {dbu} DBU/hr @ ~{active_hours} hrs/mo", vcpu=0)

    # ---- storage (low cost, flagged for completeness) --------------------- #
    if rt in ("azurerm_storage_account", "aws_s3_bucket", "google_storage_bucket"):
        return Estimate(round(_STORAGE_FLAT_USD * FX_USD_GBP, 2), 0.0, "Storage base (usage-driven; nominal)", vcpu=0)

    # ---- anything else: record it, don't price it ------------------------- #
    return Estimate(0.0, 0.0, f"No price model for {rt}", priced=False, vcpu=0)
