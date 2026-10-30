# 13F Filing Reconciler

Pulls 13F-HR filings from **SEC EDGAR** (no paid API required) for any institutional
fund manager, compares the most recent two quarters, and outputs the differences to CSV.

## What it produces

| File | Contents |
|---|---|
| `13f_changes_<CIK>_<period>.csv` | Every new, closed, and changed position sorted by absolute share-count change (largest first) |
| `13f_summary_<CIK>_<period>.csv` | Count and aggregate market value for each category |

### Detail CSV columns

| Column | Description |
|---|---|
| Category | `New`, `Closed`, or `Changed` |
| Direction | `Increase` or `Decrease` (blank for New/Closed) |
| Option Type | `Call`, `Put`, or `Equity` |
| Issuer Name (Current Quarter) | Name as reported in the current filing |
| Issuer Name (Prior Quarter) | Name as reported in the prior filing |
| CUSIP | 9-character CUSIP (stable identifier; used for cross-quarter matching) |
| Ticker | 13F filings carry no tickers; resolved from the CUSIP via OpenFIGI (see `--tickers`) |
| Prior / Current Period | Reporting period end dates |
| Prior / Current Shares | Share counts as reported |
| Share Change | Current minus prior (negative = decrease) |
| Prior / Current Market Value ($) | Market value in whole US dollars as reported (SEC switched from thousands in 2023) |
| Market Value Change ($) | Current minus prior |
| Prior / Current Filing Date | Date each 13F was filed with the SEC |
| Notes | `Name changed`, `CUSIP changed`, or blank |

### Largest movers (bottom of the summary CSV)

Top 10 per table, ranked by size, never by market value. Each asset class has its own
tables and is never summed with another: rows are matched on CUSIP + put/call + SH/PRN.

| Asset class | Tables | Ranked by |
|---|---|---|
| Equity | New, Closed, Increases, Decreases | shares |
| Calls | Increases (incl. newly opened), Decreases (incl. fully closed) | underlying shares |
| Puts | Increases (incl. newly opened), Decreases (incl. fully closed) | underlying shares |
| Bonds | New | principal amount |

Filings only report positive counts, so a change is current minus prior for the same CUSIP.
There is no minimum size: any change counts. Rows for the same CUSIP (one per sub-manager)
are summed first. A position whose count did not change is `No Change`, not an increase.

Tickers are looked up last, only for the rows in these tables (at most 90 CUSIPs), via the
free OpenFIGI API (`api.openfigi.com`; set `OPENFIGI_API_KEY` for higher limits). The detail
CSV is not looked up. If the lookup fails, tickers stay blank.

### Summary CSV rows

- New Positions
- Closed Positions
- Changed – Increase
- Changed – Decrease
- Changed – No Change (share count unchanged; value moved)
- Total Changed (all directions)
- GRAND TOTAL

## Requirements

- **Python 3.11+** — stdlib only, no `pip install` needed
- Network access to `sec.gov` and `data.sec.gov`
- A valid email address for the SEC EDGAR User-Agent header (SEC policy requirement)

## Usage

```bash
# By CIK (most reliable)
python 13f_reconciler.py --cik 0001067983

# By fund manager name (performs a search on EDGAR)
python 13f_reconciler.py --name "Berkshire Hathaway"

# Specify output directory and custom email for User-Agent
python 13f_reconciler.py --cik 0001067983 --output ./results --email you@example.com
```

### Finding a CIK

Go to https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany and search for
the fund manager. The CIK appears in the URL of their filing page.

Common CIKs:

| Fund | CIK |
|---|---|
| Berkshire Hathaway | 0001067983 |
| Renaissance Technologies | 0001037389 |
| Bridgewater Associates | 0001350694 |
| Citadel Advisors | 0001423689 |
| Tiger Global | 0001167483 |

## How cross-quarter matching works

1. **Primary key**: `(CUSIP, option_type)` — CUSIP is the stable 9-digit identifier
   assigned to each security. This correctly handles name changes and ticker changes
   between quarters.
2. **Name fallback**: If a CUSIP doesn't match (rare CUSIP reissuances), the reconciler
   falls back to a normalized issuer name match and flags the row with `CUSIP changed`.
3. Both call and put options on the same underlying are tracked separately via the
   `option_type` dimension of the key.

## Running tests

```bash
python test_reconciler.py
```

## SEC EDGAR rate limits

SEC EDGAR limits to **10 requests per second per IP**. The script sleeps 0.6 s between
requests to stay well within this limit. If you see HTTP 429 errors, increase the `delay`
parameter in `reconciler_core._get()`.

## Output example

```
Resolving CIK...
  CIK: 0001067983
Fetching 13F-HR filing list from SEC EDGAR...
  Current quarter: period=2024-12-31  filed=2025-02-14
  Prior quarter:   period=2024-09-30  filed=2024-11-14
Fetching current quarter holdings...
  46 positions
Fetching prior quarter holdings...
  49 positions
Comparing holdings...
  New: 3   Closed: 6   Changed: 38
Writing output files...
  Wrote 47 data rows → results/13f_changes_0001067983_20241231.csv
  Wrote 8 data rows  → results/13f_summary_0001067983_20241231.csv

Complete.
  Detail CSV : results/13f_changes_0001067983_20241231.csv
  Summary CSV: results/13f_summary_0001067983_20241231.csv
```
