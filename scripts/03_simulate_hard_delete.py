"""
Simulates a GDPR erasure / account closure for 2 customers.
Run AFTER the second 'dbt snapshot' run (post tier-change).

Deletes customers 44 and 50 from RAW.CUSTOMERS entirely.

After running this, run 'dbt snapshot' again. Because INVALIDATE_HARD_DELETES=TRUE
is set in the snapshot config, dbt detects the missing rows and sets DBT_VALID_TO
on their latest snapshot entries — formally closing their history.

Without that flag, deleted customers would remain as open rows (DBT_VALID_TO IS NULL)
and appear as "current" in any downstream model filtering on active customers.
"""

import os
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

deleted_ids = [44, 50]

for customer_id in deleted_ids:
    cur.execute("DELETE FROM RAW.CUSTOMERS WHERE CUSTOMER_ID = %s", (customer_id,))
    print(f"Deleted customer {customer_id} (GDPR erasure / account closure)")

cur.close()
conn.close()
print(f"\nDone. {len(deleted_ids)} customers deleted.")
print("Next: dbt snapshot  (invalidate_hard_deletes will close their snapshot rows)")
