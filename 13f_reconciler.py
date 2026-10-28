"""
13F Filing Reconciler — SEC EDGAR
Pulls 13F-HR filings for a fund manager, compares the latest two quarters,
and writes detailed + summary CSVs.

Usage examples:
    python 13f_reconciler.py --cik 0001067983                      # Berkshire Hathaway
    python 13f_reconciler.py --name "Berkshire Hathaway"
    python 13f_reconciler.py --cik 0001067983 --output ./results
    python 13f_reconciler.py --cik 0001067983 --email you@example.com

Requirements:
    Python 3.11+  (stdlib only — no pip installs needed)

SEC rate limit policy: max 10 requests/second per IP.
This script sleeps 0.6s between requests to stay well under the limit.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

import reconciler_core as rc


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

DETAIL_HEADERS = [
    "Category",
    "Direction",
    "Option Type",
    "Issuer Name (Current Quarter)",
    "Issuer Name (Prior Quarter)",
    "CUSIP",
    "Ticker",
    "Prior Period",
    "Current Period",
    "Prior Shares",
    "Current Shares",
    "Share Change",
    "Prior Market Value ($)",
    "Current Market Value ($)",
    "Market Value Change ($)",
    "Prior Filing Date",
    "Current Filing Date",
    "Notes",
]

SUMMARY_HEADERS = [
    "Category",
    "Position Count",
    "Aggregate Market Value ($)",
]


def _fmt(n: int) -> str:
    return f"{n:,}"


def _detail_row(c: rc.PositionChange) -> list:
    return [
        c.category,
        c.direction,
        c.option_type if c.option_type else "Equity",
        c.issuer_name_current,
        c.issuer_name_prior,
        c.cusip,
        c.ticker,
        c.prior_period,
        c.current_period,
        _fmt(c.prior_shares),
        _fmt(c.current_shares),
        _fmt(c.share_change),
        _fmt(c.prior_market_value),
        _fmt(c.current_market_value),
        _fmt(c.market_value_change),
        c.prior_filed,
        c.current_filed,
        c.note,
    ]


def _build_summary(changes: list[rc.PositionChange]) -> list[list]:
    buckets: dict[str, dict] = {
        "New Positions": {"count": 0, "mv": 0},
        "Closed Positions": {"count": 0, "mv": 0},
        "Changed - Increase": {"count": 0, "mv": 0},
        "Changed - Decrease": {"count": 0, "mv": 0},
    }
    for c in changes:
        if c.category == "New":
            buckets["New Positions"]["count"] += 1
            buckets["New Positions"]["mv"] += c.current_market_value
        elif c.category == "Closed":
            buckets["Closed Positions"]["count"] += 1
            buckets["Closed Positions"]["mv"] += c.prior_market_value
        elif c.category == "Changed":
            key = f"Changed - {c.direction}"
            buckets[key]["count"] += 1
            buckets[key]["mv"] += abs(c.market_value_change)

    rows = [[k, _fmt(v["count"]), _fmt(v["mv"])] for k, v in buckets.items()]

    total_changed = (
        buckets["Changed - Increase"]["count"] + buckets["Changed - Decrease"]["count"]
    )
    total_changed_mv = (
        buckets["Changed - Increase"]["mv"] + buckets["Changed - Decrease"]["mv"]
    )
    grand_total = sum(v["count"] for v in buckets.values())

    rows += [
        ["", "", ""],
        ["Total Changed (all directions)", _fmt(total_changed), _fmt(total_changed_mv)],
        ["GRAND TOTAL", _fmt(grand_total), ""],
    ]
    return rows


TOP_N = 10
TOP_HEADERS = [
    "Section", "Rank", "Ticker", "Issuer", "CUSIP", "Option Type",
    "Prior Shares", "Current Shares", "Share Change",
]
TOP_LABELS = {
    "New": "Largest New Positions (by shares)",
    "Closed": "Largest Closed Positions (by shares)",
    "Increase": "Largest Increases (by share change)",
    "Decrease": "Largest Decreases (by share change)",
}


def _top_rows(top: dict[str, list[rc.PositionChange]]) -> list[list]:
    rows: list[list] = []
    for section in rc.TOP_SECTIONS:
        rows.append([])
        for rank, c in enumerate(top[section], 1):
            rows.append([
                TOP_LABELS[section], rank, c.ticker,
                c.issuer_name_current or c.issuer_name_prior, c.cusip,
                c.option_type or "Equity",
                _fmt(c.prior_shares), _fmt(c.current_shares), _fmt(c.share_change),
            ])
    return rows


def write_csv(path: Path, headers: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  Wrote {len(rows)} data rows → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare 13F-HR filings from SEC EDGAR for a fund manager.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    id_grp = parser.add_mutually_exclusive_group(required=True)
    id_grp.add_argument("--cik", help="SEC CIK number (e.g. 0001067983)")
    id_grp.add_argument("--name", help='Fund manager name to search for (e.g. "Berkshire Hathaway")')
    parser.add_argument(
        "--output", default=".",
        help="Output directory for CSV files (default: current directory)",
    )
    parser.add_argument(
        "--email",
        help=(
            "Your email address to include in the SEC User-Agent header. "
            "SEC EDGAR policy requires a valid contact email. "
            "Defaults to the value compiled into reconciler_core.py."
        ),
    )
    parser.add_argument(
        "--tickers", choices=["top", "all", "none"], default="top",
        help=(
            "Look up tickers from CUSIPs via OpenFIGI (13F filings carry none). "
            "'top' (default) resolves only the largest-movers tables, 'all' also fills "
            "the detail CSV (slow without OPENFIGI_API_KEY), 'none' skips the lookup."
        ),
    )
    args = parser.parse_args()

    if args.email:
        rc.USER_AGENT = f"13F-Reconciler {args.email}"
        rc.HEADERS["User-Agent"] = rc.USER_AGENT

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Resolve CIK ---
    print("Resolving CIK...")
    cik = rc.resolve_cik(cik=args.cik, name=args.name)
    print(f"  CIK: {cik}")

    # --- Discover filings ---
    print("Fetching 13F-HR filing list from SEC EDGAR...")
    filings = rc.get_13f_filings(cik, max_filings=5)
    if len(filings) < 2:
        print("ERROR: Need at least 2 filings to compare.", file=sys.stderr)
        sys.exit(1)

    current_filing = filings[0]
    prior_filing = filings[1]
    print(f"  Current quarter: period={current_filing.period}  filed={current_filing.filed}")
    print(f"  Prior quarter:   period={prior_filing.period}  filed={prior_filing.filed}")

    # --- Fetch holdings ---
    print("Fetching current quarter holdings...")
    current_holdings = rc.fetch_holdings(cik, current_filing)
    print(f"  {len(current_holdings)} positions")

    print("Fetching prior quarter holdings...")
    prior_holdings = rc.fetch_holdings(cik, prior_filing)
    print(f"  {len(prior_holdings)} positions")

    # --- Compare ---
    print("Comparing holdings...")
    changes = rc.compare_holdings(prior_holdings, current_holdings, prior_filing, current_filing)

    new_c = sum(1 for c in changes if c.category == "New")
    closed_c = sum(1 for c in changes if c.category == "Closed")
    changed_c = sum(1 for c in changes if c.category == "Changed")
    print(f"  New: {new_c}   Closed: {closed_c}   Changed: {changed_c}")

    # --- Largest movers (ranked by share count) and tickers ---
    top = rc.top_movers(changes, TOP_N)
    if args.tickers != "none":
        wanted = changes if args.tickers == "all" else [c for rows in top.values() for c in rows]
        print(f"Looking up tickers for {len({c.cusip for c in wanted})} CUSIPs (OpenFIGI)...")
        tickers = rc.lookup_tickers([c.cusip for c in wanted], os.environ.get("OPENFIGI_API_KEY"))
        for c in changes:
            c.ticker = c.ticker or tickers.get(c.cusip.strip().upper(), "")
        print(f"  Resolved {len(tickers)} tickers")

    # --- Write CSVs ---
    safe_period = current_filing.period.replace("-", "")
    detail_path = out_dir / f"13f_changes_{cik}_{safe_period}.csv"
    summary_path = out_dir / f"13f_summary_{cik}_{safe_period}.csv"

    print("Writing output files...")
    write_csv(detail_path, DETAIL_HEADERS, [_detail_row(c) for c in changes])
    summary_rows = _build_summary(changes)
    write_csv(summary_path, SUMMARY_HEADERS, summary_rows)
    with open(summary_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([])
        w.writerow(TOP_HEADERS)
        w.writerows(_top_rows(top))

    print("\nComplete.")
    print(f"  Detail CSV : {detail_path}")
    print(f"  Summary CSV: {summary_path}")


if __name__ == "__main__":
    main()
