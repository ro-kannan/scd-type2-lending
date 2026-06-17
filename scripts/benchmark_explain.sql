-- Snowflake performance benchmark: point-in-time join on DIM_CUSTOMERS_SNAPSHOT.
-- Run in Snowsight (or SnowSQL) after completing all three snapshot runs.
--
-- Snowflake has no traditional B-tree indexes. Performance at scale comes from:
--   1. Micro-partition pruning — Snowflake stores data in 50–500MB compressed chunks.
--      When a column has a clustering key, Snowflake knows which partitions hold which
--      values and skips the rest. At this POC's scale (50 customers) all data fits in
--      one micro-partition — pruning is visible at 100K+ rows.
--   2. Query Profile — the primary performance diagnostic tool (Snowsight > query > Profile).
--      Shows: partitions scanned vs total, bytes spilled to disk, operator time breakdown.
--
-- The pattern documented below is what an architect presents for production scale
-- (e.g. 300K loans, 50K customers as in the Engagement 1 BFSI reference).

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 1: Run the point-in-time join WITHOUT a clustering key
--         Open Snowsight, run this, then click the Query ID → Profile tab.
--         Note: Partitions scanned = total partitions (full scan, no pruning).
-- ─────────────────────────────────────────────────────────────────────────────
EXPLAIN USING TABULAR
SELECT
    l.LOAN_ID,
    l.PRINCIPAL_AMOUNT,
    snap.RISK_TIER,
    snap.DBT_VALID_FROM,
    snap.DBT_VALID_TO
FROM DBT_LENDING.RAW.LOANS l
JOIN DBT_LENDING.SNAPSHOTS.DIM_CUSTOMERS_SNAPSHOT snap
    ON  l.CUSTOMER_ID       = snap.CUSTOMER_ID
    AND l.ORIGINATION_DATE >= snap.DBT_VALID_FROM::DATE
    AND (
        l.ORIGINATION_DATE  < snap.DBT_VALID_TO::DATE
        OR snap.DBT_VALID_TO IS NULL
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- Step 2: Add a clustering key on CUSTOMER_ID in the snapshot table.
--         At production scale this reduces partition scans to only the partitions
--         that contain the requested customer_id range.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE DBT_LENDING.SNAPSHOTS.DIM_CUSTOMERS_SNAPSHOT
    CLUSTER BY (CUSTOMER_ID);


-- ─────────────────────────────────────────────────────────────────────────────
-- Step 3: Re-run the EXPLAIN and the actual query after clustering.
--         In Snowsight Query Profile: Partitions scanned should drop vs Step 1.
--         (Visible on large datasets; at 50 rows both plans touch 1 partition.)
-- ─────────────────────────────────────────────────────────────────────────────
EXPLAIN USING TABULAR
SELECT
    l.LOAN_ID,
    l.PRINCIPAL_AMOUNT,
    snap.RISK_TIER,
    snap.DBT_VALID_FROM,
    snap.DBT_VALID_TO
FROM DBT_LENDING.RAW.LOANS l
JOIN DBT_LENDING.SNAPSHOTS.DIM_CUSTOMERS_SNAPSHOT snap
    ON  l.CUSTOMER_ID       = snap.CUSTOMER_ID
    AND l.ORIGINATION_DATE >= snap.DBT_VALID_FROM::DATE
    AND (
        l.ORIGINATION_DATE  < snap.DBT_VALID_TO::DATE
        OR snap.DBT_VALID_TO IS NULL
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- Step 4: Verify the misattribution report after all three snapshot runs.
--         misattribution_amount shows how much principal shifts between tiers
--         when you correct from naive Type 1 to point-in-time Type 2.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    RISK_TIER,
    TOTAL_PRINCIPAL_TYPE1,
    TOTAL_PRINCIPAL_TYPE2,
    MISATTRIBUTION_AMOUNT,
    LOAN_COUNT_TYPE1,
    LOAN_COUNT_TYPE2
FROM DBT_LENDING.MARTS.REPORT_REVENUE_MISATTRIBUTION
ORDER BY RISK_TIER;
