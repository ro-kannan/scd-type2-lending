"""
Simulates real-world customer risk tier changes.
Run AFTER the first 'dbt snapshot' baseline run.

Queries the actual current tiers before updating — guarantees real changes.
Changes made:
  - 3 High-Risk customers  → Standard  (credit rehabilitation)
  - 2 Standard customers   → Premium   (sustained good repayment)
"""

import os
from datetime import datetime, timezone

import snowflake.connector

conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    database=os.environ.get("SNOWFLAKE_DATABASE", "DBT_LENDING"),
    schema="RAW"
)
cur = conn.cursor()

# Find customers who are actually High-Risk and Standard right now
cur.execute("SELECT CUSTOMER_ID FROM RAW.CUSTOMERS WHERE RISK_TIER = 'High-Risk' LIMIT 3")
high_risk_ids = [row[0] for row in cur.fetchall()]

cur.execute("SELECT CUSTOMER_ID FROM RAW.CUSTOMERS WHERE RISK_TIER = 'Standard' LIMIT 2")
standard_ids = [row[0] for row in cur.fetchall()]

if len(high_risk_ids) < 3 or len(standard_ids) < 2:
    print(f"Found {len(high_risk_ids)} High-Risk and {len(standard_ids)} Standard customers")
    print("Not enough customers to simulate — check raw data")
    exit(1)

now = datetime.now(timezone.utc)

changes = (
    [(cid, 'Standard', 'credit rehabilitation after 18-month repayment streak') for cid in high_risk_ids] +
    [(cid, 'Premium',  'upgraded: 3 years of on-time payments, no defaults')    for cid in standard_ids]
)

for customer_id, new_tier, reason in changes:
    cur.execute("""
        UPDATE RAW.CUSTOMERS
           SET RISK_TIER  = %s,
               UPDATED_AT = %s
         WHERE CUSTOMER_ID = %s
    """, (new_tier, now, customer_id))
    print(f"Customer {customer_id}: → {new_tier}  ({reason})")

cur.close()
conn.close()
print(f"\nDone. {len(changes)} customers updated.")
print("Next: dbt snapshot  (SCD Type 2 rows will be created for these customers)")
