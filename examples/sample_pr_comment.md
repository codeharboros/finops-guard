## 🟥 finops-guard — cost & carbon gate: **FAIL**

This change **adds about £3,969/mo** (£47,622/yr) and **192 kgCO2e/mo**.

| | Monthly | Annual |
| --- | --- | --- |
| 💷 Cost (net) | £3,969 | £47,622 |
| 🌍 Carbon | 192 kgCO2e | 2,309 kgCO2e (≈ 13,581 km driven) |

### ❌ Must fix (2)
- **Large new monthly cost** — `azurerm_linux_virtual_machine.ml_trainer`  
  Adds about £1,765/mo (£21,176/yr). Above the £1,500 hard limit — needs explicit sign-off. Basis: Azure VM standard_nc6s_v3: 6 vCPU @ $3.06/hr list.  
  _→ Confirm the size is intended, or add an approved-cost label to override._
- **New spend with no owner / cost-centre tag** — `aws_db_instance.analytics`  
  Adds about £394/mo but carries no owner or cost-centre tag, so it cannot be attributed. Missing: environment, owner, cost_center.  
  _→ Add owner / cost_center tags before merge._

### ⚠️ Review (9)
- **Notable new monthly cost** — `databricks_sql_endpoint.bi`  
  Adds about £834/mo (£10,011/yr). Basis: Databricks SQL small: 12 DBU/hr @ ~160 hrs/mo.  
  _→ Check the SKU is right-sized for the workload._
- **Missing required tag(s)** — `databricks_cluster.etl`  
  Missing required tag(s): cost_center.  
  _→ Add cost_center to this resource._
- **Notable new monthly cost** — `databricks_cluster.etl`  
  Adds about £714/mo (£8,570/yr). Basis: Databricks 5 x standard_ds4_v2 @ ~160 hrs/mo.  
  _→ Check the SKU is right-sized for the workload._
- **Notable new monthly cost** — `aws_db_instance.analytics`  
  Adds about £394/mo (£4,734/yr). Basis: RDS db.m5.xlarge multi-AZ: 4 vCPU.  
  _→ Check the SKU is right-sized for the workload._
- **Notable new monthly cost** — `azurerm_kubernetes_cluster.platform`  
  Adds about £332/mo (£3,986/yr). Basis: AKS default pool: 3 x standard_d4s_v5 (4 vCPU each).  
  _→ Check the SKU is right-sized for the workload._
- **Missing required tag(s)** — `azurerm_linux_virtual_machine.dev_api`  
  Missing required tag(s): owner, cost_center.  
  _→ Add owner, cost_center to this resource._
- **Non-prod compute — confirm auto-shutdown** — `azurerm_linux_virtual_machine.dev_api`  
  Non-prod compute at about £111/mo. If it runs 24x7, an out-of-hours schedule would save roughly £104/mo.  
  _→ Attach an auto-shutdown / start-stop schedule for non-prod._
- **Cleaner region available** — `azurerm_linux_virtual_machine.ml_trainer`  
  About 87 kgCO2e/mo in westeurope (330 g/kWh). swedencentral is 40 g/kWh.  
  _→ If latency/residency allow, swedencentral would cut about 76 kgCO2e/mo._
- **Cleaner region available** — `aws_db_instance.analytics`  
  About 29 kgCO2e/mo in eu-central-1 (350 g/kWh). eu-north-1 is 40 g/kWh.  
  _→ If latency/residency allow, eu-north-1 would cut about 26 kgCO2e/mo._

### ℹ️ Note (1)
- **No price model for this resource type** — `azurerm_key_vault.secrets`  
  azurerm_key_vault has no estimate yet — cost/carbon not counted. Add it to the pricebook to include it.

<details><summary>Priced resources (7)</summary>

| Resource | Type | Region | £/mo | kgCO2e/mo |
| --- | --- | --- | ---: | ---: |
| `azurerm_linux_virtual_machine.ml_trainer` | azurerm_linux_virtual_machine | westeurope | 1,765 | 87 |
| `databricks_sql_endpoint.bi` | databricks_sql_endpoint | uksouth | 834 | 26 |
| `databricks_cluster.etl` | databricks_cluster | westeurope | 714 | 30 |
| `aws_db_instance.analytics` | aws_db_instance | eu-central-1 | 394 | 29 |
| `azurerm_kubernetes_cluster.platform` | azurerm_kubernetes_cluster | uksouth | 332 | 29 |
| `azurerm_linux_virtual_machine.dev_api` | azurerm_linux_virtual_machine | uksouth | 111 | 10 |
| `azurerm_container_registry.shared` | azurerm_container_registry | uksouth | 40 | 0 |

</details>

<sub>Not yet priced (excluded from totals): azurerm_key_vault.</sub>

<sub>Estimates from public list prices, deliberately conservative — a forecast, not a bill. Tune thresholds and required tags in `.finops-guard.yml`. — finops-guard</sub>
