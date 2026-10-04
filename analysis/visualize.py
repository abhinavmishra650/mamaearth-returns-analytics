"""
visualize.py
Self-contained: re-derives the cleaned data it needs directly from the raw
CSVs in data/ (same cleaning rules as clean_and_eda.py), so it can be run on
its own or after clean_and_eda.py and always regenerates the same two PNGs.

Run: python analysis/visualize.py
Writes: visualizations/return_rate_by_payment.png
        visualizations/monthly_revenue_trend.png
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VIZ_DIR = os.path.join(BASE_DIR, "visualizations")
os.makedirs(VIZ_DIR, exist_ok=True)

# --- Re-derive the cleaned frame (mirrors clean_and_eda.py Tasks 2-6) -------
customers = pd.read_csv(os.path.join(DATA_DIR, "customers.csv"))
products = pd.read_csv(os.path.join(DATA_DIR, "products.csv"))
orders = pd.read_csv(os.path.join(DATA_DIR, "orders.csv"))

orders["payment_method"] = orders["payment_method"].str.strip().str.upper()

natural_key = [
    "customer_id", "product_id", "order_date", "quantity",
    "discount_pct", "payment_method", "rating", "returned",
]
orders_clean = orders[~orders.duplicated(subset=natural_key, keep="first")].reset_index(drop=True)

rating_median = orders_clean["rating"].median()
orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)
orders_clean["rating"] = orders_clean["rating"].fillna(rating_median)

merged = orders_clean.merge(products, on="product_id").merge(customers, on="customer_id")
merged["order_value"] = merged["quantity"] * merged["price"] * (1 - merged["discount_pct"] / 100)

Q1, Q3 = merged["quantity"].quantile(0.25), merged["quantity"].quantile(0.75)
IQR = Q3 - Q1
lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
merged["is_outlier"] = (merged["quantity"] < lower) | (merged["quantity"] > upper)

merged["order_date"] = pd.to_datetime(merged["order_date"])
merged["year_month"] = merged["order_date"].dt.to_period("M").astype(str)

# ---------------------------------------------------------------------------
# Chart 1: return_rate_by_payment.png
# ---------------------------------------------------------------------------
by_payment = merged.groupby("payment_method")["returned"].mean().mul(100).round(1)
by_payment = by_payment.sort_values(ascending=False)

cod_rate = by_payment["COD"]
card_rate = by_payment["CARD"]
multiple = cod_rate / card_rate

fig, ax = plt.subplots(figsize=(7, 5))
colors = ["#d62728" if m == "COD" else "#4c72b0" for m in by_payment.index]
bars = ax.bar(by_payment.index, by_payment.values, color=colors)
for bar, val in zip(bars, by_payment.values):
    ax.text(bar.get_x() + bar.get_width() / 2, val + 0.8, f"{val:.1f}%",
            ha="center", va="bottom", fontweight="bold")
ax.set_ylabel("Return rate (%)")
ax.set_xlabel("Payment method (cleaned)")
ax.set_ylim(0, max(by_payment.values) * 1.2)
ax.set_title(f"COD Returns at {cod_rate:.1f}% \u2014 {multiple:.1f}x Card", fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(VIZ_DIR, "return_rate_by_payment.png"), dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Chart 2: monthly_revenue_trend.png (outlier-corrected, per Task 10)
# ---------------------------------------------------------------------------
monthly_corrected = merged.loc[~merged["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)
peak_month = monthly_corrected.idxmax()
peak_value = monthly_corrected[peak_month]

fig, ax = plt.subplots(figsize=(8, 5))
ax.set_ylim(0, monthly_corrected.max() * 1.28)
ax.plot(monthly_corrected.index, monthly_corrected.values, marker="o", linewidth=2, color="#2a9d8f")
peak_idx = list(monthly_corrected.index).index(peak_month)
ax.scatter([peak_month], [peak_value], color="#d62728", zorder=5, s=90)
ax.annotate(f"Peak: {peak_month}  \u20b9{peak_value:,.2f}", xy=(peak_month, peak_value),
            xytext=(peak_idx, peak_value + monthly_corrected.max() * 0.14),
            ha="center", fontweight="bold", color="#d62728")
ax.set_xlabel("Month")
ax.set_ylabel("Revenue (\u20b9, outlier-corrected)")
ax.set_title(f"Monthly Revenue (Outlier-Corrected) \u2014 {peak_month} is the True Peak Month",
             fontsize=12, fontweight="bold")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(VIZ_DIR, "monthly_revenue_trend.png"), dpi=150)
plt.close(fig)

print("Wrote visualizations/return_rate_by_payment.png")
print(by_payment.to_string())
print(f"\nWrote visualizations/monthly_revenue_trend.png")
print(monthly_corrected.to_string())
print(f"Peak month: {peak_month} at {peak_value:.2f}")
