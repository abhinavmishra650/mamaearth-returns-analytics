# Mamaearth Returns Analytics

An end-to-end pipeline proving out one thing for Mamaearth's Growth Analytics team:
**are returns eating into margins on a subset of orders, and if so, where exactly?**

Three connected layers, each one feeding the next:

1. **SQL relational layer** (`sql/`) -- loads the raw order data into SQLite and answers
   9 business questions against it.
2. **Python/pandas analysis layer** (`analysis/`) -- an independent pipeline over the same
   raw CSVs that cleans the data, reconciles its cleaned totals against Part 1's raw totals,
   runs the EDA, and writes the verified figures to `narrator/findings.json`.
3. **GenAI narrator** (`narrator/`) -- turns `findings.json` into a plain-English
   Situation-Complication-Resolution business narrative, using the Gemini API when a
   free API key is available and a fully offline template when it isn't.

**No layer reports a number it did not itself compute or receive from the layer before
it.** Layer 3 never invents a statistic -- it only narrates what Layer 2 verified, and
Layer 2's cleaned total is reconciled line-by-line against Layer 1's raw total.

```
repo/
├── README.md
├── sql/
│   ├── schema.sql        -- CREATE TABLE for customers, products, orders
│   ├── seed_data.sql     -- loads data/*.csv into those tables
│   └── reports.sql       -- the 9 business-question queries (a-i), with real output as comments
├── data/
│   ├── customers.csv     -- 45 rows, as given -- never hand-edited
│   ├── products.csv      -- 16 rows, as given -- never hand-edited
│   └── orders.csv        -- 180 rows, as given -- never hand-edited (raw, with messy casing/blanks/dupes)
├── analysis/
│   ├── clean_and_eda.py  -- pandas cleaning + EDA over the raw CSVs; writes narrator/findings.json
│   └── visualize.py      -- the 2 required charts, re-derives what it needs from the raw CSVs
├── visualizations/
│   ├── return_rate_by_payment.png
│   └── monthly_revenue_trend.png
└── narrator/
    ├── findings.json           -- written BY clean_and_eda.py, never hand-typed
    ├── generate_narrative.py   -- Gemini online path + offline fallback + numeric checker
    └── sample_output.txt       -- a saved narrative for the checker to validate (see note below)
```

## Requirements

- Python 3.10+ with `pandas` and `matplotlib` (`pip install -r requirements.txt` installs
  both, plus the optional `google-genai` package)
- SQLite 3 (the `sqlite3` CLI, or any engine that accepts the exact `CREATE TABLE` /
  `ALTER TABLE` syntax used here)
- Optional, for the online narrator path only: `google-genai` and a free Gemini API key
  from [Google AI Studio](https://aistudio.google.com/apikey)

Two small convenience files sit alongside the structure above but aren't part of the
graded pipeline itself: `requirements.txt` (Python dependencies) and `.gitignore` (so a
locally-created `mamaearth.db` or `__pycache__/` never gets committed).

## How to run, in order

### 1. SQL layer -- schema, seed data, reports

```bash
sqlite3 mamaearth.db < sql/schema.sql
sqlite3 mamaearth.db < sql/seed_data.sql
sqlite3 -header -column mamaearth.db < sql/reports.sql
```

`seed_data.sql` contains plain `INSERT` statements generated directly from the CSVs in
`data/` (not SQLite's `.import`), so blank `discount_pct`/`rating` cells load as real SQL
`NULL` from the start -- no separate `UPDATE ... WHERE col = ''` cleanup step is needed.
Re-running these three files against a fresh database file reproduces the same 45 / 16 /
180 rows and the same report output every time. `reports.sql` runs against this **raw,
uncleaned** data, exactly as the brief specifies -- Part 1 is deliberately answering its
questions before any cleaning happens in Part 2.

### 2. Python/pandas layer -- clean, reconcile, analyze, visualize

```bash
python analysis/clean_and_eda.py
python analysis/visualize.py
```

`clean_and_eda.py` is a fully independent pipeline: it reads `data/*.csv` directly, never
touches `mamaearth.db`, and can be run before or after Part 1. It standardizes
`payment_method` casing, drops the 5 duplicate orders, imputes missing `discount_pct`/
`rating`, merges and reconciles its cleaned revenue total against Part 1's raw total
(explaining the exact ₹2,501.90 gap), flags quantity outliers with IQR, tests two
hypotheses, and prints a full outlier-corrected monthly revenue trend. **Its last step
writes `narrator/findings.json`** -- the one file Part 3 is allowed to read numbers from.

`visualize.py` re-derives the same cleaned frame from the raw CSVs (so it's runnable on
its own) and saves the two required charts to `visualizations/`.

### 3. GenAI narrator -- turn findings.json into a business narrative

```bash
# Online (Gemini): set a free API key first
export GEMINI_API_KEY=your_free_aistudio_key_here
python narrator/generate_narrative.py

# Offline (no key, no network, no cost): just don't set a key
unset GEMINI_API_KEY GOOGLE_API_KEY
python narrator/generate_narrative.py
```

`generate_scr_narrative()` in `generate_narrative.py` is the single entry point: it checks
for `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) and calls the live Gemini API
(`temperature=0.0`, an explicit `max_output_tokens`, a 15-second timeout, the whole call
wrapped in `try/except`) when a key is present, and **automatically falls back** to
`generate_scr_narrative_offline()` -- a zero-network, zero-key, f-string template built
directly from `findings.json` -- whenever no key is configured or the online call fails
for any reason. Either way the script also runs `check_numeric_accuracy()`, which prints
a PASS/FAIL line for each of the 5 figures Task 5 requires, against both the narrative it
just generated and the saved `narrator/sample_output.txt`.

> **Note on the model name:** the online path calls `gemini-flash-latest`, Google's
> maintained alias for its current free-tier-eligible Flash model, specifically so this
> code doesn't need editing every time Google renames or retires a dated model string.
> If your AI Studio account's free tier ever points you at a different model name, change
> the single `model=` line in `generate_scr_narrative()`.

> **Note on `sample_output.txt`:** the brief asks for a real, saved Gemini response here
> because live LLM output isn't byte-for-byte reproducible. The narrative saved in that
> file is a real Gemini response, generated in the Google AI Studio chat from the same
> instructions and the same figures that `generate_narrative.py` builds from
> `findings.json`, and it passes all five checks in `check_numeric_accuracy()`. Running
> `generate_narrative.py` with a `GEMINI_API_KEY` produces a similar (not identical)
> narrative; with no key it uses the offline template.

## Reproducing every number in this brief

1. Run the SQL block above -- `reports.sql`'s output matches the comments already in that
   file (total revenue ₹99,860.20, the Jaipur/Lucknow/Bangalore return-rate outliers, the
   top-5 spenders, etc.).
2. Run `clean_and_eda.py` -- every intermediate number it prints (duplicate count, median
   rating, IQR bounds, correlation bands, monthly revenue with and without outliers) is
   also checked with an `assert`, so a silent regression would fail loudly instead of
   quietly producing a wrong number.
3. Run `visualize.py` -- the two PNGs in `visualizations/` are generated from that same
   cleaned data, not drawn by hand.
4. Run `generate_narrative.py` -- the narrative it prints (online or offline) is built
   only from `narrator/findings.json`, which was itself written by step 2, not hand-typed.
