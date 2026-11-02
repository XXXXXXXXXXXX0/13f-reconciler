# 13F Filing Reconciler

Pulls 13F-HR filings from **SEC EDGAR** (no paid API required) for any institutional
fund manager, compares the most recent two quarters, and outputs the differences to CSV.

## Latest results

Updated automatically by each committed run (`13f_reconciler.py` rewrites the text between the
markers below). It shows whichever fund was run most recently.

<!-- latest-results:start -->
CIK **0001009207**, period **2026-06-30** compared with **2026-03-31**. Full tables: [`results/0001009207_2026-06-30/13f_summary_0001009207_2026-06-30.csv`](results/0001009207_2026-06-30/13f_summary_0001009207_2026-06-30.csv).

**Top equity increases (≥ +50%)**

| # | Ticker | Issuer | Prior shares | Current shares | % change |
|---|---|---|---:|---:|---:|
| 1 | EWZ | ISHARES INC | 12,380 | 7,120,968 | +57,419.9% |
| 2 | XLE | SELECT SECTOR SPDR TR | 16,440 | 7,531,605 | +45,712.7% |
| 3 | AEIS | ADVANCED ENERGY INDS | 1,600 | 585,573 | +36,498.3% |
| 4 | HLT | HILTON WORLDWIDE HLDGS INC | 807 | 240,298 | +29,676.7% |
| 5 | VUG | VANGUARD INDEX FDS | 1,424 | 201,707 | +14,064.8% |
| 6 | DELL | DELL TECHNOLOGIES INC | 7,629 | 973,711 | +12,663.3% |
| 7 | CACI | CACI INTL INC | 1,246 | 157,665 | +12,553.7% |
| 8 | DOCN | DIGITALOCEAN HLDGS INC | 7,000 | 880,572 | +12,479.6% |
| 9 | RYAAY | RYANAIR HOLDINGS PLC | 5,400 | 644,450 | +11,834.3% |
| 10 | INTU | INTUIT | 17,929 | 2,135,509 | +11,810.9% |

**Top equity decreases (≥ −33%)**

| # | Ticker | Issuer | Prior shares | Current shares | % change |
|---|---|---|---:|---:|---:|
| 1 | HOOD | ROBINHOOD MKTS INC | 2,873,569 | 14,600 | -99.5% |
| 2 | BABA | ALIBABA GROUP HLDG LTD | 726,244 | 4,473 | -99.4% |
| 3 | AZO | AUTOZONE INC | 44,034 | 364 | -99.2% |
| 4 | CRCL | CIRCLE INTERNET GROUP INC | 2,734,925 | 27,976 | -99.0% |
| 5 | OPEN | OPENDOOR TECHNOLOGIES INC | 11,230,177 | 121,686 | -98.9% |
| 6 | RVMD | REVOLUTION MEDICINES INC | 1,022,298 | 12,400 | -98.8% |
| 7 | VRTX | VERTEX PHARMACEUTICALS INC | 248,960 | 3,105 | -98.8% |
| 8 | MSI | MOTOROLA SOLUTIONS INC | 92,443 | 1,600 | -98.3% |
| 9 | ARM | ARM HOLDINGS PLC | 306,620 | 5,764 | -98.1% |
| 10 | AAOI | APPLIED OPTOELECTRONICS INC | 2,117,157 | 41,056 | -98.1% |
<!-- latest-results:end -->

## What it produces

| File | Contents |
|---|---|
| `results/<CIK>_<period>/13f_changes_<CIK>_<period>.csv` | Every new, closed, and changed position sorted by absolute share-count change (largest first) |
| `results/<CIK>_<period>/13f_summary_<CIK>_<period>.csv` | Count and aggregate market value for each category, then the top-10 tables |
| `tickers/<CIK>_<period>.json` | Tickers for the top-10 tables' CUSIPs, reused on later runs of the same period |

### Detail CSV columns

| Column | Description |
|---|---|
| Category | `New`, `Closed`, or `Changed` |
| Direction | `Increase` or `Decrease` (blank for New/Closed) |
| Security Type | `Equity`, `Call`, `Put`, or `Bond` (reported as a principal amount) |
| Issuer Name (Current Quarter) | Name as reported in the current filing |
| Issuer Name (Prior Quarter) | Name as reported in the prior filing |
| CUSIP | 9-character CUSIP (stable identifier; used for cross-quarter matching) |
| Ticker | 13F filings carry no tickers. Filled from the ticker store for every row whose CUSIP appears in the top-10 tables (calls and puts share their underlying's CUSIP); other rows are blank by design. For bonds this is the issuer's ticker, with OpenFIGI's full bond identifier in Notes |
| Prior / Current Period | Reporting period end dates |
| Prior / Current Shares | Share counts as reported |
| Share Change | Current minus prior (negative = decrease) |
| % Change | Share change as % of prior shares (blank for New/Closed) |
| Prior / Current Market Value ($) | Market value in whole US dollars as reported (SEC switched from thousands in 2023) |
| Market Value Change ($) | Current minus prior |
| Prior / Current Filing Date | Date each 13F was filed with the SEC |
| Notes | `Name changed`, `CUSIP changed`, `OpenFIGI security: …` (bond identifier), or blank |

### Largest movers (bottom of the summary CSV)

Top 10 per table, never ranked by market value. Equity increases and decreases rank by % change
from the prior filing; all other tables rank by share count (principal for bonds). Each asset class has its own
tables and is never summed with another: rows are matched on CUSIP + put/call + SH/PRN.

| Asset class | Tables | Ranked by |
|---|---|---|
| Equity | New, Closed (shares); Increases, Decreases (% change) | see left |
| Calls | New, Closed, Increases, Decreases | underlying shares |
| Puts | New, Closed, Increases, Decreases | underlying shares |
| Bonds | New | principal amount |

New / Closed means the CUSIP appears in only one of the two filings. Increase / Decrease means
it appears in both, and the change is current minus prior shares (filings only report positive
counts). Price is never a criterion: a position with the same share count is left out even if
its value moved. Rows for the same CUSIP (one per sub-manager) are summed first.

**Equity thresholds** (`EQUITY_MIN_INCREASE_PCT` / `EQUITY_MIN_DECREASE_PCT` in
`reconciler_core.py`): an equity position held in both filings counts only if shares rose at
least **50%** or fell at least **33%** versus the prior filing. These two are the same size of
move in each direction (100 → 150 is +50%; 150 → 100 is −33%). There is no dollar floor. The
thresholds apply to the detail CSV, the summary counts and the tables. Calls, puts and bonds are
not filtered.

Tickers are looked up last, only for the CUSIPs in these tables, via the free OpenFIGI API
(`api.openfigi.com`; set `OPENFIGI_API_KEY` for higher limits). Identifiers starting with a
letter are sent as non-US CINS codes. The detail CSV is never looked up.

### Ticker store (`tickers/<CIK>_<period>.json`)

Before calling OpenFIGI, the run reads the store for that CIK and filing period:

- **Same period:** stored tickers are reused, and only CUSIPs never asked about are looked up.
  A repeat run of the same quarter makes zero OpenFIGI calls.
- **New period:** a new file starts empty, so that quarter's CUSIPs are looked up fresh. This
  picks up mergers, renames and restructurings. Earlier periods' files are left as they are.
- CUSIPs OpenFIGI has no match for are stored under `not_found` and not retried in that period.
- If a lookup errors partway (network, rate limit), the run stops with an error and writes and
  commits nothing. A re-run reuses what is stored and retries the rest.

### Saved results and commits

Each complete run writes its CSVs to `results/<CIK>_<period>/` and the ticker store to
`tickers/`, then commits exactly those files with the message
`13F run: CIK <CIK>, period <period>` and pushes the current branch. A run that fails before the
end commits nothing. If nothing changed since the last committed run, no commit is made. Use
`--no-commit` to write files without committing.

### Summary CSV rows

- New Positions
- Closed Positions
- Changed – Increase
- Changed – Decrease
- Changed – No Change (share count unchanged; kept only for a name/CUSIP-change note)
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

# Custom email for the SEC User-Agent; write files without committing
python 13f_reconciler.py --cik 0001067983 --email you@example.com --no-commit
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
python test_reconciler.py      # or: pytest -q test_reconciler.py
```

GitHub Actions (`.github/workflows/tests.yml`) runs the tests on every push and pull request.
The tests need no network access.

## Commit messages

Say what changed and why: a short summary line, then the reasons in the body. Commits made by
a run are always `13F run: CIK <CIK>, period <period>`.

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
