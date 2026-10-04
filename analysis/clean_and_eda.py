"""
clean_and_eda.py
Independent pandas pipeline over the RAW source CSVs in data/ -- does not touch
the SQL database in any way, so this can be run before or after Part 1.

Run: python analysis/clean_and_eda.py
Writes: narrator/findings.json (the verified figures Part 3 narrates)
"""

import json
import os
import pandas as pd

pd.set_option("display.width", 120)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
NARRATOR_DIR = os.path.join(BASE_DIR, "narrator")


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# Task 1 -- Load and inspect (2 marks)
# ---------------------------------------------------------------------------
section("Task 1: Load and inspect")

customers = pd.read_csv(os.path.join(DATA_DIR, "customers.csv"))
products = pd.read_csv(os.path.join(DATA_DIR, "products.csv"))
orders = pd.read_csv(os.path.join(DATA_DIR, "orders.csv"))

print(f"customers.shape = {customers.shape}")
print(f"products.shape  = {products.shape}")
print(f"orders.shape    = {orders.shape}")
assert orders.shape == (180, 9), "orders.csv should have 180 rows and 9 columns before cleaning"


# ---------------------------------------------------------------------------
# Task 2 -- Standardize payment_method casing (4 marks)
# ---------------------------------------------------------------------------
section("Task 2: Standardize payment_method casing")

raw_values = sorted(orders["payment_method"].unique())
print(f"Raw distinct values ({len(raw_values)}): {raw_values}")
assert len(raw_values) == 7, "expected 7 distinct raw casings of payment_method"

orders["payment_method"] = orders["payment_method"].str.strip().str.upper()

clean_values = sorted(orders["payment_method"].unique())
print(f"Cleaned distinct values ({len(clean_values)}): {clean_values}")
assert len(clean_values) == 3

counts = orders["payment_method"].value_counts()
print("Counts after cleaning:")
print(counts.to_string())
assert counts.to_dict() == {"CARD": 70, "UPI": 55, "COD": 55}


# ---------------------------------------------------------------------------
# Task 3 -- Remove duplicate orders (4 marks)
# ---------------------------------------------------------------------------
section("Task 3: Remove duplicate orders")

natural_key = [
    "customer_id", "product_id", "order_date", "quantity",
    "discount_pct", "payment_method", "rating", "returned",
]

is_dup = orders.duplicated(subset=natural_key, keep="first")
dropped_rows = orders[is_dup].copy()
dropped_order_ids = sorted(dropped_rows["order_id"].tolist())
print(f"Flagged {len(dropped_order_ids)} duplicate rows (natural key: {natural_key})")
print(f"Dropped order_id values: {dropped_order_ids}")
assert dropped_order_ids == ["O0176", "O0177", "O0178", "O0179", "O0180"]

orders_clean = orders[~is_dup].reset_index(drop=True)
print(f"orders_clean.shape = {orders_clean.shape}")
assert orders_clean.shape == (175, 9)


# ---------------------------------------------------------------------------
# Task 4 -- Impute missing values (4 marks)
# ---------------------------------------------------------------------------
section("Task 4: Impute missing values")

discount_missing = orders_clean["discount_pct"].isnull().sum()
print(f"discount_pct missing on deduplicated frame: {discount_missing} rows")
assert discount_missing == 12
orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)

rating_median = orders_clean["rating"].median()
rating_missing = orders_clean["rating"].isnull().sum()
print(f"rating median BEFORE imputing (deduplicated frame): {rating_median}")
print(f"rating missing on deduplicated frame: {rating_missing} rows")
assert rating_median == 3.0
assert rating_missing == 15
orders_clean["rating"] = orders_clean["rating"].fillna(rating_median)

null_check = orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict()
print(f"Null counts after imputing: {null_check}")
assert null_check == {"discount_pct": 0, "rating": 0}


# ---------------------------------------------------------------------------
# Task 5 -- Merge and reconcile against Part 1 (5 marks)
# ---------------------------------------------------------------------------
section("Task 5: Merge and reconcile against Part 1")

merged = orders_clean.merge(products, on="product_id").merge(customers, on="customer_id")
merged["order_value"] = merged["quantity"] * merged["price"] * (1 - merged["discount_pct"] / 100)

cleaned_total = round(merged["order_value"].sum(), 2)
print(f"Total order_value across {len(merged)} cleaned rows: {cleaned_total:.2f}")
assert abs(cleaned_total - 97358.30) < 0.01

raw_total = 99860.20  # from Part 1, Report (a), against the raw 180-row table
delta = round(raw_total - cleaned_total, 2)
print(f"Part 1 raw total_revenue (Report a): {raw_total:.2f}")
print(f"Delta (raw - cleaned): {delta:.2f}")

# Independent check: sum order_value for the 5 dropped rows on their own,
# using the same formula, and confirm it equals the delta above.
dropped_merged = dropped_rows.merge(products, on="product_id").merge(customers, on="customer_id")
dropped_merged["order_value"] = (
    dropped_merged["quantity"] * dropped_merged["price"] * (1 - dropped_merged["discount_pct"].fillna(0) / 100)
)
dropped_total = round(dropped_merged["order_value"].sum(), 2)
print(f"Independent check -- combined order_value of the 5 dropped duplicate rows: {dropped_total:.2f}")
assert abs(dropped_total - delta) < 0.01

print(
    f"\nReconciliation note: The cleaned pipeline's total order_value of Rs.{cleaned_total:.2f} is exactly "
    f"Rs.{delta:.2f} less than Part 1 Report (a)'s raw total of Rs.{raw_total:.2f}. This entire delta is "
    f"attributable to the 5 duplicate order rows (order_id O0176-O0180) removed in Task 3 above: summing "
    f"order_value for just those 5 rows independently gives Rs.{dropped_total:.2f}, which matches the delta "
    f"exactly. The delta is NOT attributable to the discount_pct/rating imputation performed in Task 4 -- "
    f"filling a missing discount_pct or rating with a default/median value only changes rows that previously "
    f"had no order_value contribution decided by that field's absence, and none of the 5 duplicate rows had a "
    f"missing discount_pct or rating in the first place (each had concrete values), so imputation contributes "
    f"Rs.0.00 to this delta. Removing duplicate rows is a strictly separate operation from imputing missing "
    f"values, and only the former moves the revenue total."
)


# ---------------------------------------------------------------------------
# Task 6 -- IQR outlier detection on quantity (4 marks)
# ---------------------------------------------------------------------------
section("Task 6: IQR outlier detection on quantity")

Q1 = merged["quantity"].quantile(0.25)
Q3 = merged["quantity"].quantile(0.75)
IQR = Q3 - Q1
lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR
print(f"Q1={Q1}, Q3={Q3}, IQR={IQR}, lower_bound={lower}, upper_bound={upper}")
assert (Q1, Q3, IQR, lower, upper) == (1.0, 2.0, 1.0, -0.5, 3.5)

merged["is_outlier"] = (merged["quantity"] < lower) | (merged["quantity"] > upper)
outliers = merged.loc[merged["is_outlier"], ["order_id", "quantity", "order_date"]]
print(f"Outlier rows ({merged['is_outlier'].sum()}):")
print(outliers.to_string(index=False))
assert sorted(outliers["order_id"].tolist()) == ["O0011", "O0098"]
print("NOTE: these rows are flagged, not dropped -- Task 9/Task 10 below use the is_outlier flag.")


# ---------------------------------------------------------------------------
# Task 7 -- Hypothesis: does COD have a higher return rate? (4 marks)
# ---------------------------------------------------------------------------
section("Task 7: Hypothesis -- does COD have a higher return rate?")

print(
    "Hypothesis: Cash-on-Delivery (COD) orders have a higher return rate than prepaid "
    "methods (CARD, UPI), because a customer who has not already paid has less friction "
    "in rejecting/returning an item at the doorstep."
)
by_payment = merged.groupby("payment_method")["returned"].agg(["count", "mean"])
by_payment["return_rate_pct"] = (by_payment["mean"] * 100).round(1)
print(by_payment[["count", "return_rate_pct"]].to_string())

rates = by_payment["return_rate_pct"].to_dict()
assert rates == {"CARD": 14.7, "COD": 44.4, "UPI": 18.9}
print(
    f"\nResult: Hypothesis CONFIRMED. COD return rate ({rates['COD']}%) is roughly 3x CARD "
    f"({rates['CARD']}%) and well above UPI ({rates['UPI']}%)."
)


# ---------------------------------------------------------------------------
# Task 8 -- Multi-level segmentation (4 marks)
# ---------------------------------------------------------------------------
section("Task 8: Multi-level segmentation (payment_method x city_tier)")

seg = merged.groupby(["payment_method", "city_tier"])["returned"].agg(["count", "mean"])
seg["return_rate_pct"] = (seg["mean"] * 100).round(1)
print(seg[["count", "return_rate_pct"]].to_string())

cod_tier1 = seg.loc[("COD", 1)]
cod_tier2 = seg.loc[("COD", 2)]
print(
    f"\nCOD in Tier-1 cities: {int(cod_tier1['count'])} orders at {cod_tier1['return_rate_pct']}% returned"
)
print(
    f"COD in Tier-2 cities: {int(cod_tier2['count'])} orders at {cod_tier2['return_rate_pct']}% returned"
)

highest_key = seg["return_rate_pct"].idxmax()
highest_rate = seg["return_rate_pct"].max()
print(
    f"\nHighest-risk segment: payment_method={highest_key[0]}, city_tier={highest_key[1]}, "
    f"return_rate_pct={highest_rate}%"
)
assert highest_key == ("COD", 2)
assert highest_rate == 54.5
assert int(cod_tier1["count"]) == 32 and cod_tier1["return_rate_pct"] == 37.5
assert int(cod_tier2["count"]) == 22 and cod_tier2["return_rate_pct"] == 54.5
print(
    "This shows COD risk is NOT uniform across tiers: a single blended COD rate (44.4%, Task 7) "
    "hides that Tier-2 COD orders return at 54.5% vs 37.5% for Tier-1 COD orders -- the real "
    "problem concentrates in Tier-2 COD, not COD in general."
)


# ---------------------------------------------------------------------------
# Task 9 -- Correlation analysis (2 marks)
# ---------------------------------------------------------------------------
section("Task 9: Correlation analysis")

corr = merged[["rating", "returned", "discount_pct", "quantity"]].corr()
print(corr.round(3).to_string())


def band(r):
    r = abs(r)
    if r < 0.2:
        return "negligible"
    elif r < 0.4:
        return "weak"
    elif r < 0.7:
        return "moderate"
    else:
        return "strong"


cols = ["rating", "returned", "discount_pct", "quantity"]
print("\nPairwise strength bands (0-0.19 negligible / 0.2-0.39 weak / 0.4-0.69 moderate / 0.7-1.0 strong):")
all_negligible = True
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        a, b = cols[i], cols[j]
        r = corr.loc[a, b]
        b_label = band(r)
        if b_label != "negligible":
            all_negligible = False
        print(f"  {a} vs {b}: r={r:.3f} -> {b_label}")

disc_ret_corr = corr.loc["discount_pct", "returned"]
print(f"\ndiscount_pct vs returned correlation = {disc_ret_corr:.3f}")
assert -0.15 < disc_ret_corr < -0.05
assert all_negligible, "expected all six pairs to be negligible"
print(
    f'Hypothesis "higher discounts reduce returns" is BUSTED -- the correlation ({disc_ret_corr:.2f}) '
    f"is negligible in magnitude, not the moderate-to-strong negative relationship the hypothesis needs."
)
print("All six pairwise correlations fall in the negligible band (|r| < 0.2).")


# ---------------------------------------------------------------------------
# Task 10 -- Outlier-corrected time series (4 marks)
# ---------------------------------------------------------------------------
section("Task 10: Outlier-corrected time series")

merged["order_date"] = pd.to_datetime(merged["order_date"])
merged["year_month"] = merged["order_date"].dt.to_period("M").astype(str)

monthly_with_outliers = merged.groupby("year_month")["order_value"].sum().round(2)
print("Monthly revenue INCLUDING the two Task 6 outlier orders:")
print(monthly_with_outliers.to_string())

monthly_without_outliers = (
    merged.loc[~merged["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)
)
print("\nMonthly revenue EXCLUDING the two Task 6 outlier orders (outlier-corrected):")
print(monthly_without_outliers.to_string())

peak_with = monthly_with_outliers.idxmax()
peak_without = monthly_without_outliers.idxmax()
print(f"\nApparent peak month (with outliers):  {peak_with} at {monthly_with_outliers[peak_with]:.2f}")
print(f"True peak month (outlier-corrected):  {peak_without} at {monthly_without_outliers[peak_without]:.2f}")

o0011_date = merged.loc[merged["order_id"] == "O0011", "order_date"].dt.strftime("%Y-%m-%d").iloc[0]
o0098_date = merged.loc[merged["order_id"] == "O0098", "order_date"].dt.strftime("%Y-%m-%d").iloc[0]
print(
    f"\nNOTE: January's apparent lead ({monthly_with_outliers['2026-01']:.2f}) is an artifact of the two "
    f"bulk orders from Task 6 both landing in January: O0011 (quantity 25, dated {o0011_date}) and O0098 "
    f"(quantity 30, dated {o0098_date}). Once these outliers are excluded, January drops to "
    f"{monthly_without_outliers['2026-01']:.2f}, and March emerges as the genuine peak month at "
    f"{monthly_without_outliers['2026-03']:.2f} -- this is exactly why Task 6 (flagging outliers) had to "
    f"happen before Task 10 (trending revenue), not after."
)

assert peak_with == "2026-01" and abs(monthly_with_outliers["2026-01"] - 29582.10) < 0.01
assert abs(monthly_with_outliers["2026-06"] - 11615.40) < 0.01
assert peak_without == "2026-03" and abs(monthly_without_outliers["2026-03"] - 20318.90) < 0.01
assert abs(monthly_without_outliers["2026-01"] - 11637.10) < 0.01
assert abs(monthly_without_outliers["2026-02"] - 13195.50) < 0.01
assert abs(monthly_without_outliers["2026-04"] - 9495.30) < 0.01
assert abs(monthly_without_outliers["2026-05"] - 13151.10) < 0.01
assert abs(monthly_without_outliers["2026-06"] - 11615.40) < 0.01


# ---------------------------------------------------------------------------
# Task 1 (Part 3) -- Export narrator/findings.json
# ---------------------------------------------------------------------------
section("Exporting narrator/findings.json (Part 3, Task 1)")

findings = {
    "cleaned_total_revenue_inr": round(cleaned_total, 2),
    "raw_total_revenue_inr": round(raw_total, 2),
    "duplicate_reconciliation_delta_inr": round(delta, 2),
    "return_rate_by_payment": {
        "COD": rates["COD"],
        "CARD": rates["CARD"],
        "UPI": rates["UPI"],
    },
    "highest_risk_segment": {
        "payment_method": highest_key[0],
        "city_tier": int(highest_key[1]),
        "return_rate_pct": float(highest_rate),
    },
    "true_peak_month": {
        "month": peak_without,
        "revenue_inr": round(float(monthly_without_outliers[peak_without]), 2),
    },
    "outlier_inflated_month": {
        "month": peak_with,
        "apparent_revenue_inr": round(float(monthly_with_outliers[peak_with]), 2),
        "corrected_revenue_inr": round(float(monthly_without_outliers[peak_with]), 2),
    },
}

os.makedirs(NARRATOR_DIR, exist_ok=True)
findings_path = os.path.join(NARRATOR_DIR, "findings.json")
with open(findings_path, "w") as f:
    json.dump(findings, f, indent=2)

print(f"Wrote {findings_path}:")
print(json.dumps(findings, indent=2))

section("clean_and_eda.py complete -- all assertions passed")
