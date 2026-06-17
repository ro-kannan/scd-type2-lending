# SCD Type 2 — Historical Risk Attribution (dbt + Snowflake)

> **7 dbt models · 3-layer architecture · 19 data quality tests · Snowflake**  
> Staging → SCD Type 2 Snapshot → Gold Dimensions → Fact Tables + Misattribution Report

When a lending customer moves from High-Risk to Standard, their historical loans should still be reported under High-Risk — that was the risk profile at origination. A naive join to the current dimension table silently re-labels them as Standard, understating portfolio risk in exactly the periods that credit committees and regulators scrutinise. No error is thrown. Finance cannot explain the reconciliation gap.

This project builds the production-pattern fix using dbt's native snapshot feature and produces a concrete dollar figure showing how much principal moves between risk buckets when you correct from Type 1 to Type 2.

---

## The Broader Pattern — This Problem Appears Everywhere

Risk tier misattribution in lending is one instance of a universal data modelling problem: **any dimension attribute that changes over time will corrupt historical fact reporting if the dimension is not versioned.**

| Industry | Dimension | Attribute that changes | Reporting impact |
|----------|-----------|----------------------|-----------------|
| **Retail / E-commerce** | Product | Category (e.g. "Electronics" → "Clearance") | Revenue by category overstated for Clearance, understated for Electronics — historical sales mix looks cleaner than it was, buying decisions get distorted |
| **Retail / E-commerce** | Customer | Loyalty tier (Silver → Gold) | Discount attribution and LTV calculations wrong for periods before the upgrade |
| **HR / Payroll** | Employee | Grade or department | Finance cannot reconcile cost centre headcount or salary band reports across periods |
| **Insurance** | Policy | Risk class or premium band | Claims-to-premium ratios wrong for reclassified policies — actuarial models built on this data are flawed |
| **Telecom** | Customer | Plan / tariff | Revenue per plan mixes current and historical subscribers — churn and ARPU trends are meaningless |
| **SaaS** | Account | Subscription tier or CSM segment | Renewal and expansion revenue attributed to the wrong tier — quota calculations and cohort analysis break |

**The reconciliation problem compounds over time.** When Finance or a regulator asks "why does this quarter's number not match what we reported last quarter for the same period?" — the answer is almost always a dimension updated in place (Type 1) rather than versioned (Type 2). The further back the question goes, the harder it is to reconstruct what the data looked like at that point in time. This is one of the most common root causes of unexplained variance in period-over-period reporting.

This project uses customer risk tiers in lending as a concrete, quantifiable example. The architecture applies directly to any row in the table above.

---

## Architecture

```
RAW.CUSTOMERS (Snowflake)          RAW.LOANS (Snowflake)
        │                                   │
        ▼                                   │
stg_customers (staging view)        stg_loans (staging view)
        │                                   │
        ▼                                   │
dim_customers_snapshot                      │
  (dbt snapshot — SCD Type 2,             │
   invalidate_hard_deletes=True)            │
        │                                   │
        ├──► dim_customers                  │
        │    (current state, 1 row/customer)│
        │                                   │
        └──► dim_customers_history ◄────────┤
             (full history, 1 row/version)  │
                    │                       │
                    └───────────────────────┤
                                            │
             ┌──────────────────────────────┘
             │
             ├──► fct_loans_type1       (naive — current tier join)
             ├──► fct_loans_type2       (correct — point-in-time join + surrogate key)
             └──► report_revenue_misattribution
```

**Stack:** Python 3.13 · dbt-core 1.11 · dbt-snowflake · Snowflake

---

## What It Demonstrates

### Two failure modes of Type 1 (naive) reporting

**Failure 1 — Tier misclassification:**
A loan originated when a customer was High-Risk should be reported under High-Risk for the life of the loan. Under Type 1, if that customer later moves to Standard, the loan is re-attributed to Standard. Risk teams and credit committees base capital allocation decisions on tier-level principal totals — silent misattribution in this number is a material reporting error with regulatory consequences.

**Failure 2 — Deleted record impact (GDPR / account closure):**
When a customer is removed from the source system, they disappear from the current dimension table. Under Type 1, every loan tied to that customer loses its tier attribution — principal surfaces as unresolvable in reports, creating a reconciliation gap Finance cannot close without digging into raw history. This gap widens with each GDPR erasure or account closure processed. Type 2 preserves the historical record in the snapshot regardless of what happens to the source row.

### How Type 2 fixes both

The dbt snapshot captures every tier change as a versioned row with `dbt_valid_from` / `dbt_valid_to` timestamps. Loans are joined to the snapshot version that was valid on the origination date:

```sql
on  l.customer_id      = snap.customer_id
and l.origination_date >= snap.dbt_valid_from::date
and (
    l.origination_date  < snap.dbt_valid_to::date
    or snap.dbt_valid_to is null
)
```

Hard deletes are handled via `invalidate_hard_deletes=True` — when a customer row disappears from the source, dbt closes their snapshot entry by setting `dbt_valid_to`. Their historical loans remain correctly attributed; only their presence in the live `dim_customers` is removed. Even after a GDPR erasure, historical risk attribution is intact.

### Sample output — misattribution report

After running, query `DBT_LENDING.MARTS.REPORT_REVENUE_MISATTRIBUTION`:

| risk_tier | total_principal_type1 | total_principal_type2 | misattribution_amount | loan_count_type1 | loan_count_type2 |
|---|---|---|---|---|---|
| High-Risk | 1,240,000 | 1,890,000 | +650,000 | 18 | 27 |
| Standard | 2,100,000 | 1,780,000 | −320,000 | 31 | 26 |
| Premium | 3,560,000 | 3,230,000 | −330,000 | 52 | 48 |
| Deleted / Unresolved | 68,000 | 0 | −68,000 | 1 | 0 |

*(Illustrative — actual values vary with each random data generation run)*

Reading the table: High-Risk principal is **understated under Type 1** — those loans now appear under Standard or Premium because the customer's tier improved after origination. The `Deleted / Unresolved` row is the deleted-record failure: Type 1 has no way to attribute this principal because the customer no longer exists in the current dimension. Type 2 recovers it correctly via the snapshot.

---

## Design Decisions

**1. dbt snapshot over hand-rolled MERGE**
dbt's `snapshot` block handles the insert/update/close logic automatically and integrates with the dbt DAG — lineage, tests, and docs work out of the box. A hand-rolled MERGE requires maintaining the timestamp comparison logic, the open/close update, and concurrent-run safeguards manually. For teams already on dbt Core or Cloud, snapshot is the standard choice.

For reference, the equivalent hand-rolled MERGE (what dbt compiles down to internally):
```sql
MERGE INTO dim_customers_history AS target
USING (SELECT *, CURRENT_TIMESTAMP AS new_valid_from FROM raw.customers) AS source
ON target.customer_id = source.customer_id AND target.dbt_valid_to IS NULL
WHEN MATCHED AND source.risk_tier != target.risk_tier THEN
    UPDATE SET target.dbt_valid_to = source.new_valid_from
WHEN NOT MATCHED THEN
    INSERT (customer_id, risk_tier, dbt_valid_from, dbt_valid_to, ...)
    VALUES (source.customer_id, source.risk_tier, source.new_valid_from, NULL, ...);
```

**2. Two gold dimension tables over one**
`dim_customers` (current state, `WHERE dbt_valid_to IS NULL`) serves operational dashboards — clean, one-row-per-customer, no SCD complexity exposed to BI consumers. `dim_customers_history` (full SCD2 history) serves point-in-time queries and audit use cases. Separating them gives downstream consumers the simplest interface that meets their need, without forcing BI developers to filter SCD metadata themselves.

Marts reference `dim_customers` for current-state needs and never reference staging models directly — staging is a contract between source and snapshot, not a consumer-facing layer.

**3. Two implementation patterns for point-in-time BI joins**

Both patterns are built into the fact table so the trade-off can be demonstrated directly:

*Option A — Denormalized attribute (`risk_tier_at_origination`):*
Resolved at dbt build time and embedded in `fct_loans_type2`. BI tools join to `dim_customers` via `customer_id` for non-changing attributes; historical tier is already in the fact row. Simple, works with any BI tool. Best when only a small number of attributes change slowly.

*Option B — Surrogate key join (`customer_snapshot_key`):*
`fct_loans_type2` also carries `customer_snapshot_key` (aliased from dbt's internal `dbt_scd_id`). In Power BI, the semantic model relationship `fct_loans_type2.customer_snapshot_key = dim_customers_history.customer_snapshot_key` is a standard single-column join — no date-range logic in the BI layer. All historical dimension attributes are available to DAX measures automatically. This is the architecturally correct pattern when the dimension has many slowly-changing attributes, as it avoids denormalizing each one into the fact table.

Power BI cannot express date-range joins as model relationships — Option B is the production solution for historical reporting in semantic models.

**4. `invalidate_hard_deletes=True`**
Without this flag, a customer deleted from the source remains as an open row (`dbt_valid_to IS NULL`) in the snapshot and continues to appear as a current active customer in any downstream query filtering on current records. With the flag, dbt detects the missing row on the next run and closes it. This is required for any GDPR erasure or account closure workflow — the default behaviour leaves ghost records in the dimension.

---

## Production Gaps (Deliberately Not Built)

Calling these out explicitly because production SCD Type 2 implementations fail at these edges more often than at the core logic:

| Gap | Production Answer |
|-----|------------------|
| Concurrent snapshot runs | dbt Cloud scheduler or an Airflow mutex — two simultaneous runs can produce duplicate open rows for the same key |
| Same-batch double change | If a customer changes tier twice between snapshot runs, only the latest state is captured — intermediate state is lost. Requires higher-frequency snapshots or a true CDC source |
| `dbt_scd_id` stability | `dbt_scd_id` is an MD5 hash of `(unique_key + dbt_valid_from)`. Dropping and recreating the snapshot table regenerates new hashes — fact tables storing `customer_snapshot_key` from the old table are now pointing at non-existent keys. Treat the snapshot table as permanent in production |
| GDPR history purge | `invalidate_hard_deletes` closes the snapshot row but does not delete it — historical rows remain. A separate purge job is needed for full right-to-erasure compliance where even historical records must be removed |
| Pre-snapshot origination dates | In this POC, loans with origination dates predating the first snapshot run have no matching snapshot window and produce a NULL tier. In production with a long-running snapshot, this edge case does not arise |

---

## Data Simulation

Three scripts simulate a realistic snapshot lifecycle:

| Script | What it does |
|--------|-------------|
| `scripts/01_generate_raw_data.py` | Generates 50 customers with risk tiers + 150 loans into `DBT_LENDING.RAW` |
| `scripts/02_simulate_tier_change.py` | Queries actual current tiers before updating — moves 3 High-Risk → Standard, 2 Standard → Premium |
| `scripts/03_simulate_hard_delete.py` | Hard-deletes 2 customers from `RAW.CUSTOMERS` (simulates GDPR erasure / account closure) |

Run order: load → baseline snapshot → tier changes → second snapshot → deletions → third snapshot → `dbt run` + `dbt test`

---

## How to Run

**Prerequisites:** Python 3.13, Snowflake account, `DBT_LENDING` database with `RAW` schema

```bash
# 1. Clone and set up environment
git clone <repo-url>
cd scd-type2-lending
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Set Snowflake credentials
export SNOWFLAKE_ACCOUNT=your-account
export SNOWFLAKE_USER=your-user
export SNOWFLAKE_PASSWORD=your-password

# 3. Configure dbt profile
cp dbt_lending/profiles.yml.example dbt_lending/profiles.yml
# Edit profiles.yml with your Snowflake credentials

# 4. Load raw data
python scripts/01_generate_raw_data.py

# 5. Baseline snapshot (50 rows, all open — dbt_valid_to IS NULL)
.venv/bin/dbt snapshot --project-dir dbt_lending --profiles-dir dbt_lending

# 6. Simulate tier changes
python scripts/02_simulate_tier_change.py

# 7. Second snapshot — SCD Type 2 rows created (55 rows: 5 closed + 5 new open)
.venv/bin/dbt snapshot --project-dir dbt_lending --profiles-dir dbt_lending

# 8. Simulate hard deletes (GDPR erasure)
python scripts/03_simulate_hard_delete.py

# 9. Third snapshot — deleted customers closed by invalidate_hard_deletes
.venv/bin/dbt snapshot --project-dir dbt_lending --profiles-dir dbt_lending

# 10. Build all 7 models and run 19 data quality tests
.venv/bin/dbt run --project-dir dbt_lending --profiles-dir dbt_lending
.venv/bin/dbt test --project-dir dbt_lending --profiles-dir dbt_lending
```

**What to look at after running:**
```sql
-- The headline output: Type 1 vs Type 2 principal attribution side by side
SELECT * FROM DBT_LENDING.MARTS.REPORT_REVENUE_MISATTRIBUTION ORDER BY RISK_TIER;

-- SCD Type 2 history: see closed and open rows per customer
SELECT CUSTOMER_ID, RISK_TIER, DBT_VALID_FROM, DBT_VALID_TO
FROM DBT_LENDING.SNAPSHOTS.DIM_CUSTOMERS_SNAPSHOT
ORDER BY CUSTOMER_ID, DBT_VALID_FROM;

-- Surrogate key in the fact table (Option B join pattern for Power BI)
SELECT CUSTOMER_ID, CUSTOMER_SNAPSHOT_KEY, RISK_TIER_AT_ORIGINATION, PRINCIPAL_AMOUNT
FROM DBT_LENDING.MARTS.FCT_LOANS_TYPE2
LIMIT 20;
```

**Reset:** Drop the snapshot table and re-run from step 4:
```sql
DROP TABLE IF EXISTS DBT_LENDING.SNAPSHOTS.DIM_CUSTOMERS_SNAPSHOT;
```
