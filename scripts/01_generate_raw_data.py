"""
Generates raw lending data directly into Snowflake's RAW schema.

Creates two tables in DBT_LENDING.RAW:
  - CUSTOMERS (50 rows)  — risk_tier + updated_at drive the SCD Type 2 story
  - LOANS     (150 rows) — origination_date is what we join against snapshot history

Credentials via env vars:
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
  SNOWFLAKE_WAREHOUSE (default: COMPUTE_WH)
  SNOWFLAKE_DATABASE  (default: DBT_LENDING)
"""

import os
import random
from datetime import datetime, timedelta, timezone

import snowflake.connector
from faker import Faker

fake = Faker('en_IN')
random.seed(42)
Faker.seed(42)

conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    database=os.environ.get("SNOWFLAKE_DATABASE", "DBT_LENDING"),
    schema="RAW"
)
cur = conn.cursor()

cur.execute("CREATE DATABASE IF NOT EXISTS DBT_LENDING")
cur.execute("USE DATABASE DBT_LENDING")
cur.execute("CREATE SCHEMA IF NOT EXISTS RAW")
cur.execute("USE SCHEMA RAW")
print("Database and schema ready")

# --- Customers (50 rows) ---
# risk_tier is the column that changes; updated_at is what the dbt snapshot tracks.
# When a tier changes in 02_simulate_tier_change.py, updated_at is bumped — dbt
# detects the change, closes the old snapshot row, and opens a new one.
cur.execute("DROP TABLE IF EXISTS CUSTOMERS")
cur.execute("""
    CREATE TABLE CUSTOMERS (
        CUSTOMER_ID         INTEGER PRIMARY KEY,
        FULL_NAME           VARCHAR,
        EMAIL               VARCHAR,
        CITY                VARCHAR,
        RISK_TIER           VARCHAR,
        MEMBER_SINCE        DATE,
        UPDATED_AT          TIMESTAMP_NTZ,
        _FIVETRAN_SYNCED    TIMESTAMP_NTZ,
        _FIVETRAN_DELETED   BOOLEAN
    )
""")

tiers = ['Standard', 'Premium', 'High-Risk']
tier_weights = [50, 30, 20]
cities = ['Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Hyderabad',
          'Pune', 'Kolkata', 'Ahmedabad', 'Surat', 'Jaipur']

now = datetime.now(timezone.utc)
customers = []
for i in range(1, 51):
    member_since = fake.date_between(start_date='-4y', end_date='-6m')
    tier = random.choices(tiers, weights=tier_weights)[0]
    updated_at = fake.date_time_between(
        start_date=datetime.combine(member_since, datetime.min.time()),
        end_date=now - timedelta(days=60)
    )
    customers.append((
        i,
        fake.name(),
        fake.email(),
        random.choice(cities),
        tier,
        member_since,
        updated_at,
        now,
        False
    ))

cur.executemany("""
    INSERT INTO CUSTOMERS
        (CUSTOMER_ID, FULL_NAME, EMAIL, CITY, RISK_TIER, MEMBER_SINCE,
         UPDATED_AT, _FIVETRAN_SYNCED, _FIVETRAN_DELETED)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""", customers)
print(f"Inserted {len(customers)} customers")

# --- Loans (150 rows) ---
# principal_amount varies by loan type — gives the misattribution report
# meaningful numbers per tier rather than uniform amounts.
cur.execute("DROP TABLE IF EXISTS LOANS")
cur.execute("""
    CREATE TABLE LOANS (
        LOAN_ID             INTEGER PRIMARY KEY,
        CUSTOMER_ID         INTEGER,
        LOAN_TYPE           VARCHAR,
        PRINCIPAL_AMOUNT    NUMBER(14, 2),
        ORIGINATION_DATE    DATE,
        STATUS              VARCHAR,
        _FIVETRAN_SYNCED    TIMESTAMP_NTZ
    )
""")

loan_types = ['Personal', 'SMB', 'Home', 'Auto']
loan_type_weights = [40, 20, 25, 15]

principal_ranges = {
    'Personal': (50000,   500000),
    'SMB':      (500000,  5000000),
    'Home':     (2000000, 10000000),
    'Auto':     (300000,  1500000),
}

statuses = ['active', 'closed', 'defaulted']
status_weights = [60, 30, 10]

customer_ids = [c[0] for c in customers]

loans = []
for i in range(1, 151):
    customer_id = random.choice(customer_ids)
    loan_type = random.choices(loan_types, weights=loan_type_weights)[0]
    lo, hi = principal_ranges[loan_type]
    principal = round(random.uniform(lo, hi), 2)
    origination_date = fake.date_between(start_date='-2y', end_date='-1d')
    loans.append((
        i,
        customer_id,
        loan_type,
        principal,
        origination_date,
        random.choices(statuses, weights=status_weights)[0],
        now
    ))

cur.executemany("""
    INSERT INTO LOANS
        (LOAN_ID, CUSTOMER_ID, LOAN_TYPE, PRINCIPAL_AMOUNT,
         ORIGINATION_DATE, STATUS, _FIVETRAN_SYNCED)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
""", loans)
print(f"Inserted {len(loans)} loans")

cur.close()
conn.close()
print("\nDone. Next: dbt snapshot (baseline run)")
