-- reports.sql
-- Run after schema.sql + seed_data.sql have loaded the raw, UNCLEANED data.
-- Every query below was actually executed against that raw data in SQLite 3.45.1;
-- the output pasted in each comment block is the real result of that run, not a
-- hand-typed estimate.

-- ============================================================================
-- a) Order totals (2 marks)
-- Revenue per row = quantity * price * (1 - discount_pct/100), NULL discount
-- treated as 0% via COALESCE. Joins orders to products.
--
-- Result:
-- total_orders  total_revenue  avg_order_value
-- ------------  -------------  ---------------
-- 180           99860.2        554.78
-- ============================================================================
SELECT
    COUNT(*) AS total_orders,
    ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_revenue,
    ROUND(AVG(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS avg_order_value
FROM orders o
JOIN products p ON o.product_id = p.product_id;


-- ============================================================================
-- b) COUNT(*) vs COUNT(column) (2 marks)
-- COUNT(*) counts all rows; COUNT(rating) skips NULLs, so the gap is exactly
-- how many orders have never been rated.
--
-- Result:
-- total_orders  rated_orders  missing_ratings
-- ------------  ------------  ---------------
-- 180           165           15
-- ============================================================================
SELECT
    COUNT(*) AS total_orders,
    COUNT(rating) AS rated_orders,
    COUNT(*) - COUNT(rating) AS missing_ratings
FROM orders;


-- ============================================================================
-- c) LEFT JOIN with a genuine zero-match row (3 marks)
-- Query 1: LEFT JOIN so customers with no matching orders survive as a row
-- with COUNT(order_id) = 0 (COUNT on the joined key, not COUNT(*), so the
-- single NULL-order row per unmatched customer is not counted as an order).
-- Query 2: an independent NOT IN check against DISTINCT customer_id in
-- orders, to confirm the LEFT JOIN result rather than trust it blindly.
--
-- Result (both queries):
-- customer_id  name
-- -----------  ------
-- C045         Vihaan
-- ============================================================================
SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name
HAVING COUNT(o.order_id) = 0;

SELECT customer_id, name
FROM customers
WHERE customer_id NOT IN (SELECT DISTINCT customer_id FROM orders);


-- ============================================================================
-- d) GROUP BY + HAVING (3 marks)
-- Return rate by city; SQLite allows referencing the SELECT-list alias
-- (return_rate_pct) directly in HAVING, so the filter reads the same as the
-- computed column instead of repeating the expression.
--
-- Result (return_rate_pct > 20, ORDER BY return_rate_pct DESC):
-- city       total_orders  returned_orders  return_rate_pct
-- ---------  ------------  ---------------  ---------------
-- Jaipur     19            8                42.1
-- Lucknow    49            15               30.6
-- Bangalore  33            8                24.2
--
-- (Mumbai 17.9% and Delhi 17.4% fall below the 20% threshold and are correctly excluded.)
-- ============================================================================
SELECT
    c.city,
    COUNT(o.order_id) AS total_orders,
    SUM(o.returned) AS returned_orders,
    ROUND(100.0 * SUM(o.returned) / COUNT(o.order_id), 1) AS return_rate_pct
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY c.city
HAVING return_rate_pct > 20
ORDER BY return_rate_pct DESC;


-- ============================================================================
-- e) Ranking with ORDER BY + LIMIT/OFFSET (3 marks)
-- Tie-break note: ORDER BY total_spend DESC, customer_id ASC. Without the
-- secondary sort on customer_id, any two customers who happened to tie on
-- total_spend could come back in a different order on different runs or
-- engines (SQLite does not guarantee a stable order among ties), which would
-- make the LIMIT 3 OFFSET 2 query below unreliable for "ranks 3-5" -- the
-- explicit tie-break makes the ranking deterministic and reproducible.
--
-- Result (LIMIT 5):
-- customer_id  name     total_spend
-- -----------  -------  -----------
-- C043         Reyansh  12920.0
-- C026         Isha     8371.6
-- C008         Meera    4564.6
-- C011         Arjun    4111.0
-- C042         Sanya    3785.0
--
-- Result (LIMIT 3 OFFSET 2 -- ranks 3-5, same 5 rows, no re-derivation):
-- customer_id  name     total_spend
-- -----------  -------  -----------
-- C008         Meera    4564.6
-- C011         Arjun    4111.0
-- C042         Sanya    3785.0
-- ============================================================================
SELECT
    c.customer_id,
    c.name,
    ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_spend
FROM orders o
JOIN products p ON o.product_id = p.product_id
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 5;

SELECT
    c.customer_id,
    c.name,
    ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_spend
FROM orders o
JOIN products p ON o.product_id = p.product_id
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 3 OFFSET 2;


-- ============================================================================
-- f) Three-table JOIN with GROUP BY (3 marks)
-- orders + products + customers all joined (customers isn't strictly needed
-- for a category rollup, but the join is included to confirm the three-way
-- join compiles and returns the same rows cleanly, since Part 3's findings
-- reference figures that ultimately depend on all three tables being joinable).
--
-- Result (ORDER BY category_revenue DESC):
-- category      order_count  category_revenue
-- ------------  -----------  ----------------
-- Haircare      54           44956.1
-- Skincare      60           27346.0
-- Babycare      30           16805.0
-- PersonalCare  36           10753.1
-- ============================================================================
SELECT
    p.category,
    COUNT(o.order_id) AS order_count,
    ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS category_revenue
FROM orders o
JOIN products p ON o.product_id = p.product_id
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY p.category
ORDER BY category_revenue DESC;


-- ============================================================================
-- g) LIKE pattern match (2 marks)
--
-- Result: exactly 10 rows -- C001 Aarav, C003 Aditi, C004 Ananya, C011 Arjun,
-- C021 Aryan, C030 Anika, C031 Aditya, C036 Aisha, C041 Ayaan, C044 Aria.
-- ============================================================================
SELECT customer_id, name
FROM customers
WHERE name LIKE 'A%';


-- ============================================================================
-- h) DISTINCT (1 mark)
--
-- Result: exactly 4 values -- Ad, Organic, Referral, Social.
-- ============================================================================
SELECT DISTINCT acquisition_source
FROM customers
ORDER BY acquisition_source;


-- ============================================================================
-- i) ALTER TABLE + UPDATE with CASE (1 mark)
-- Single UPDATE, no WHERE clause -- every customer gets a tier.
--
-- Result:
-- loyalty_tier  COUNT(*)
-- ------------  --------
-- Gold          28
-- Silver        17
-- ============================================================================
ALTER TABLE customers ADD COLUMN loyalty_tier VARCHAR(10);

UPDATE customers
SET loyalty_tier = CASE WHEN city_tier = 1 THEN 'Gold' ELSE 'Silver' END;

SELECT loyalty_tier, COUNT(*)
FROM customers
GROUP BY loyalty_tier;
