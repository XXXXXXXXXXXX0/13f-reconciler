"""
Unit tests for 13F reconciler logic using synthetic 13F XML data.
Run: python test_reconciler.py
"""

import json
import subprocess
import sys
import tempfile
import textwrap
from urllib.error import HTTPError
from pathlib import Path

# Synthetic 13F information-table XML (mirrors the SEC EDGAR format)
PRIOR_XML = textwrap.dedent("""\
<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin/viewer?action=view&amp;cik=1067983&amp;type=13F-HR">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>150000</value>
    <shrsOrPrnAmt><sshPrnamt>900000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>900000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>80000</value>
    <shrsOrPrnAmt><sshPrnamt>200000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>200000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>EXXON MOBIL CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>30231G102</cusip>
    <value>40000</value>
    <shrsOrPrnAmt><sshPrnamt>400000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>400000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>10000</value>
    <shrsOrPrnAmt><sshPrnamt>50000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall>Call</putCall>
    <votingAuthority><Sole>50000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>
""")

CURRENT_XML = textwrap.dedent("""\
<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin/viewer?action=view&amp;cik=1067983&amp;type=13F-HR">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>175000</value>
    <shrsOrPrnAmt><sshPrnamt>1050000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>1050000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORPORATION</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>72000</value>
    <shrsOrPrnAmt><sshPrnamt>175000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>175000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>AMAZON COM INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>023135106</cusip>
    <value>55000</value>
    <shrsOrPrnAmt><sshPrnamt>300000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall></putCall>
    <votingAuthority><Sole>300000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>9500</value>
    <shrsOrPrnAmt><sshPrnamt>48000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <putCall>Call</putCall>
    <votingAuthority><Sole>48000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>
""")

# Import functions under test
sys.path.insert(0, str(Path(__file__).parent))
from reconciler_core import (
    parse_info_table_xml, compare_holdings, FilingMeta, Holding,
    aggregate_holdings, top_movers, lookup_tickers, apply_equity_thresholds, TickerLookup,
    pick_filing_pair,
)
import run_store


def make_filing(period: str, filed: str) -> FilingMeta:
    return FilingMeta(accession="", period=period, filed=filed, primary_doc="")


def test_parse():
    holdings = parse_info_table_xml(PRIOR_XML)
    assert len(holdings) == 4, f"Expected 4, got {len(holdings)}"
    apple = next(h for h in holdings if "APPLE" in h.issuer_name)
    assert apple.shares == 900_000
    assert apple.market_value == 150_000
    assert apple.option_type == ""

    nvda = next(h for h in holdings if "NVIDIA" in h.issuer_name)
    assert nvda.option_type == "Call"
    print("  parse_info_table_xml: PASS")


def test_compare():
    prior = parse_info_table_xml(PRIOR_XML)
    current = parse_info_table_xml(CURRENT_XML)
    pf = make_filing("2024-09-30", "2024-11-14")
    cf = make_filing("2024-12-31", "2025-02-14")
    changes = compare_holdings(prior, current, pf, cf)

    cats = {c.category for c in changes}
    assert "New" in cats, "Expected a New position (Amazon)"
    assert "Closed" in cats, "Expected a Closed position (Exxon)"
    assert "Changed" in cats, "Expected Changed positions"

    new_pos = [c for c in changes if c.category == "New"]
    assert len(new_pos) == 1
    assert "AMAZON" in new_pos[0].issuer_name_current.upper()

    closed = [c for c in changes if c.category == "Closed"]
    assert len(closed) == 1
    assert "EXXON" in closed[0].issuer_name_prior.upper()

    changed = [c for c in changes if c.category == "Changed"]
    apple_chg = next(c for c in changed if "APPLE" in c.issuer_name_current.upper())
    assert apple_chg.direction == "Increase"
    assert apple_chg.share_change == 150_000

    msft_chg = next(c for c in changed if "MICROSOFT" in c.issuer_name_current.upper())
    assert msft_chg.direction == "Decrease"
    assert msft_chg.note == "Name changed"

    nvda_chg = next(c for c in changed if "NVIDIA" in c.issuer_name_current.upper())
    assert nvda_chg.option_type == "Call"
    assert nvda_chg.direction == "Decrease"

    # Verify sorted by abs share change descending
    abs_changes = [abs(c.share_change) for c in changes]
    assert abs_changes == sorted(abs_changes, reverse=True), "Not sorted by abs share change"

    print("  compare_holdings: PASS")
    print(f"  Results: {len(new_pos)} new, {len(closed)} closed, {len(changed)} changed")
    for c in changes:
        name = c.issuer_name_current or c.issuer_name_prior
        print(f"    [{c.category:7s}] {c.direction:8s} {name:30s} "
              f"shares_chg={c.share_change:+,}  opt={c.option_type or 'equity'}")


def H(name, cusip, shares, mv=0, opt="", st="SH"):
    return Holding(name, cusip, "", opt, shares, st, mv, "SOLE", shares, 0, 0)


def test_duplicate_cusip_rows_are_summed():
    """One CUSIP on several rows (per sub-manager) must be summed, not overwritten."""
    prior = [H("ACME", "111111111", 100, 10), H("ACME", "111111111", 300, 30)]
    current = [H("ACME", "111111111", 150, 15), H("ACME", "111111111", 100, 10)]
    assert aggregate_holdings(prior)[0].shares == 400
    changes = compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b"))
    assert len(changes) == 1
    assert changes[0].prior_shares == 400 and changes[0].current_shares == 250
    assert changes[0].share_change == -150 and changes[0].direction == "Decrease"
    print("  duplicate CUSIP aggregation: PASS")


def test_name_fallback_does_not_match_across_option_types():
    """A new put must not be treated as a CUSIP change of the same issuer's common stock."""
    prior = [H("ACME", "111111111", 100)]
    current = [H("ACME", "222222222", 100, opt="Put")]
    cats = sorted(c.category for c in compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b")))
    assert cats == ["Closed", "New"]
    print("  name fallback respects option type: PASS")


def test_top_movers_rank_by_shares_not_value():
    prior = [H("BIG VALUE", "A", 100, 9_000_000), H("MANY SHARES", "B", 100, 1_000),
             H("GONE SMALL", "C", 5, 9_000_000), H("GONE BIG", "D", 5_000, 1_000)]
    current = [H("NEW SMALL", "E", 10, 9_000_000), H("NEW BIG", "F", 9_000, 1_000),
               H("BIG VALUE", "A", 150, 99_000_000), H("MANY SHARES", "B", 40_100, 1_500),
               H("BOND", "G", 99_999_999, 5, st="PRN")]
    changes = compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b"))
    top = top_movers(changes, 5)
    assert [c.issuer_name_current for c in top[("Equity", "New")]] == ["NEW BIG", "NEW SMALL"]
    assert [c.issuer_name_prior for c in top[("Equity", "Closed")]] == ["GONE BIG", "GONE SMALL"]
    assert [c.issuer_name_current for c in top[("Equity", "Increase")]] == ["MANY SHARES", "BIG VALUE"]
    assert top[("Equity", "Decrease")] == []
    assert [c.issuer_name_current for c in top[("Bond", "New")]] == ["BOND"]
    assert all(c.share_type == "SH" for k, rows in top.items() if k[0] != "Bond" for c in rows)
    print("  top_movers by share count: PASS")


def test_decrease_is_computed_from_prior_filing():
    """Filings report positive counts only; a cut shows up as current - prior < 0."""
    changes = compare_holdings([H("CUT", "Z", 1_000)], [H("CUT", "Z", 400)],
                               make_filing("a", "a"), make_filing("b", "b"))
    assert changes[0].share_change == -600 and changes[0].direction == "Decrease"
    assert top_movers(changes)[("Equity", "Decrease")][0].share_change == -600
    print("  decrease computed vs prior: PASS")


def test_options_ranked_separately_from_equity():
    """Calls/puts are never summed with the stock and get their own tables."""
    prior = [H("ACME", "A", 1_000), H("ACME", "A", 500, opt="Call"), H("ZED", "Z", 900, opt="Put")]
    current = [H("ACME", "A", 1_000), H("ACME", "A", 50_000, opt="Call"), H("ACME", "A", 7_000, opt="Put")]
    changes = compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b"))
    top = top_movers(changes)
    assert top[("Equity", "Increase")] == []                      # stock count unchanged
    assert [c.share_change for c in top[("Call", "Increase")]] == [49_500]
    # CUSIP absent from the prior filing = New, not an increase (and vice versa)
    assert [c.category for c in top[("Put", "New")]] == ["New"]
    assert [c.category for c in top[("Put", "Closed")]] == ["Closed"]
    assert top[("Put", "Increase")] == [] and top[("Put", "Decrease")] == []
    print("  options ranked separately: PASS")


def test_unchanged_share_count_is_not_an_increase():
    changes = compare_holdings([H("FLAT", "F", 100, 10)], [H("FLAT", "F", 100, 99)],
                               make_filing("a", "a"), make_filing("b", "b"))
    assert changes == []  # value moved, share count did not: not a position change
    print("  unchanged count not an increase: PASS")


def test_equity_thresholds_and_pct_ranking():
    """Equity: keep >= +50% and <= -33%; rank by %. Options are not filtered."""
    prior = [H("UP49", "A", 100), H("UP50", "B", 100), H("TINY", "C", 807),
             H("DN32", "D", 1_000), H("DN33", "E", 1_000), H("BIGDN", "F", 9_000_000), H("DN90", "H", 1_000),
             H("OPT", "G", 100, opt="Call")]
    current = [H("UP49", "A", 149), H("UP50", "B", 150), H("TINY", "C", 240_298),
               H("DN32", "D", 680), H("DN33", "E", 670), H("BIGDN", "F", 4_000_000), H("DN90", "H", 100),
               H("OPT", "G", 101, opt="Call")]
    changes = apply_equity_thresholds(
        compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b")))
    names = {c.issuer_name_current for c in changes}
    assert names == {"UP50", "TINY", "DN33", "BIGDN", "DN90", "OPT"}
    top = top_movers(changes)
    assert [c.issuer_name_current for c in top[("Equity", "Increase")]] == ["TINY", "UP50"]
    # DN90 (-900 shares, -90%) outranks BIGDN (-5M shares, -55.6%): % not share count
    assert [c.issuer_name_current for c in top[("Equity", "Decrease")]] == ["DN90", "BIGDN", "DN33"]
    print("  equity thresholds and % ranking: PASS")


def test_lookup_tickers_with_mocked_openfigi():
    calls = []

    def fake_post(url, jobs, headers):
        calls.append(len(jobs))
        out = []
        for j in jobs:
            assert j["idType"] == ("ID_CINS" if j["idValue"][0].isalpha() else "ID_CUSIP")
            if j["idValue"] == "AAA":
                out.append({"data": [{"ticker": "AAA.F", "exchCode": "GR"},
                                     {"ticker": "AAA", "exchCode": "US"}]})
            else:
                out.append({"warning": "No identifier found."})
        return out

    got = lookup_tickers(["aaa", "AAA", "BBB"] + [f"{i}X" for i in range(11)],
                         post=fake_post, sleep=lambda s: None)
    assert got.found == {"AAA": "AAA"} and not got.failed
    assert got.not_found == {"BBB"} | {f"{i}X" for i in range(11)}
    assert calls == [10, 3]          # de-duplicated, batched 10 per request without a key

    tries = []

    def limited_then_ok(url, jobs, headers):
        tries.append(1)
        if len(tries) < 3:
            raise HTTPError(url, 429, "Too Many Requests", {}, None)
        return [{"data": [{"ticker": "AAA", "exchCode": "US"}]}]
    assert lookup_tickers(["AAA"], post=limited_then_ok, sleep=lambda s: None).found == {"AAA": "AAA"}

    def boom(url, jobs, headers):
        raise OSError("blocked")
    failed = lookup_tickers(["AAA"], post=boom, sleep=lambda s: None)
    assert failed.failed and failed.found == {} and failed.not_found == set()
    print("  lookup_tickers: PASS")


# ---------------------------------------------------------------------------
# Ticker store and per-run commit
# ---------------------------------------------------------------------------

class FakeLookup:
    """Stands in for OpenFIGI and records every CUSIP it is asked about."""
    def __init__(self, known, failed=False):
        self.known, self.failed, self.calls = known, failed, []

    def __call__(self, cusips):
        self.calls.append(list(cusips))
        found = {c: self.known[c] for c in cusips if c in self.known}
        missing = set() if self.failed else set(cusips) - set(found)
        return TickerLookup(found=found, not_found=missing, failed=self.failed)


def test_same_period_reuses_store_without_lookup():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        first = FakeLookup({"AAA": "AA", "BBB": "BB"})
        res = run_store.resolve_tickers(["AAA", "BBB", "ZZZ"], "0001", "2026-06-30", root, first)
        run_store.write_json(run_store.ticker_store_path("0001", "2026-06-30", root), res.store)
        assert first.calls == [["AAA", "BBB", "ZZZ"]]

        again = FakeLookup({})
        res2 = run_store.resolve_tickers(["AAA", "BBB", "ZZZ"], "0001", "2026-06-30", root, again)
        assert again.calls == []                       # zero OpenFIGI calls
        assert res2.tickers == {"AAA": "AA", "BBB": "BB"}
        assert res2.store["not_found"] == ["ZZZ"]      # not-found is remembered, not retried
    print("  ticker store reused within a period: PASS")


def test_only_missing_cusips_are_looked_up():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        run_store.write_json(run_store.ticker_store_path("0001", "2026-06-30", root),
                             {"tickers": {"AAA": "AA"}, "not_found": ["ZZZ"]})
        lookup = FakeLookup({"CCC": "CC"})
        res = run_store.resolve_tickers(["AAA", "ZZZ", "CCC"], "0001", "2026-06-30", root, lookup)
        assert lookup.calls == [["CCC"]]
        assert res.tickers == {"AAA": "AA", "CCC": "CC"}
        assert res.store["tickers"] == {"AAA": "AA", "CCC": "CC"}
    print("  only missing CUSIPs looked up: PASS")


def test_new_period_does_fresh_lookup():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        old_path = run_store.ticker_store_path("0001", "2026-06-30", root)
        run_store.write_json(old_path, {"tickers": {"AAA": "OLD"}, "not_found": ["ZZZ"]})
        lookup = FakeLookup({"AAA": "NEW", "ZZZ": "ZZ"})
        res = run_store.resolve_tickers(["AAA", "ZZZ"], "0001", "2026-09-30", root, lookup)
        assert lookup.calls == [["AAA", "ZZZ"]]        # prior quarter's file is not used
        assert res.tickers == {"AAA": "NEW", "ZZZ": "ZZ"}
        assert json.loads(old_path.read_text())["tickers"] == {"AAA": "OLD"}
    print("  new period looked up fresh: PASS")


def test_failed_lookup_is_flagged_and_not_recorded_as_not_found():
    with tempfile.TemporaryDirectory() as d:
        res = run_store.resolve_tickers(["AAA"], "0001", "2026-06-30", Path(d),
                                        FakeLookup({}, failed=True))
        assert res.failed and res.store["not_found"] == []
    print("  failed lookup flagged: PASS")


def test_commit_run_commits_only_run_files():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        git = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (root / "unrelated.txt").write_text("x")
        git("add", "unrelated.txt")                    # staged, but not part of the run
        out = root / "results" / "0001_2026-06-30" / "a.csv"
        out.parent.mkdir(parents=True)
        out.write_text("a\n")
        assert run_store.commit_run([out], "13F run: CIK 0001, period 2026-06-30",
                                    root, push=False) == "committed"
        files = git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
        assert files == ["results/0001_2026-06-30/a.csv"]
        assert run_store.commit_run([out], "again", root, push=False) == "unchanged"
    print("  commit_run commits only run files: PASS")


def test_readme_latest_results_section():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        readme = root / "README.md"
        readme.write_text(f"# X\n\n{run_store.README_START}\nold\n{run_store.README_END}\n\n## Rest\n")
        changes = compare_holdings([H("UPCO", "A", 100), H("DNCO", "B", 1_000)],
                                   [H("UPCO", "A", 400), H("DNCO", "B", 100)],
                                   make_filing("2026-03-31", "x"), make_filing("2026-06-30", "y"))
        top = top_movers(changes)
        top[("Equity", "Increase")][0].ticker = "UPC"
        summary = root / "results" / "0001_2026-06-30" / "s.csv"
        section = run_store.render_latest_results("0001", "2026-06-30", "2026-03-31", top, summary, root)
        assert "| 1 | UPC | UPCO | 100 | 400 | +300.0% |" in section
        assert "| 1 | — | DNCO | 1,000 | 100 | -90.0% |" in section
        assert "results/0001_2026-06-30/s.csv" in section

        assert run_store.update_readme(readme, section) is True
        text = readme.read_text()
        assert "old" not in text and text.startswith("# X") and text.endswith("## Rest\n")
        assert run_store.update_readme(readme, section) is False   # same run: no change
    print("  README latest-results section: PASS")


def test_detail_rows_security_type_and_tickers():
    """Bonds are labelled Bond; resolved tickers fill every row sharing the CUSIP."""
    import importlib
    cli = importlib.import_module("13f_reconciler")
    prior = [H("ACME", "AAA", 100), H("ACME", "AAA", 50, opt="Call"), H("OTHER", "OOO", 10)]
    current = [H("ACME", "AAA", 400), H("ACME", "AAA", 90, opt="Call"), H("OTHER", "OOO", 99),
               H("SUPER MICRO", "86800UAF1", 372_692_000, st="PRN")]
    changes = compare_holdings(prior, current, make_filing("a", "a"), make_filing("b", "b"))
    run_store.apply_tickers(changes, {"AAA": "ACM", "86800UAF1": "SMCI 0 06/15/30"})
    rows = {(r[5], r[2]): r for r in map(cli._detail_row, changes)}
    col = cli.DETAIL_HEADERS.index
    assert cli.DETAIL_HEADERS[2] == "Security Type"
    bond = rows[("86800UAF1", "Bond")]
    assert bond[col("Ticker")] == "SMCI"
    assert bond[col("Notes")] == "OpenFIGI security: SMCI 0 06/15/30"
    assert rows[("AAA", "Equity")][col("Ticker")] == "ACM"
    assert rows[("AAA", "Call")][col("Ticker")] == "ACM"       # option shares the CUSIP
    assert rows[("OOO", "Equity")][col("Ticker")] == ""        # never looked up: stays blank
    print("  detail security type and tickers: PASS")


def test_pick_filing_pair():
    f = lambda period, filed: FilingMeta(accession=filed, period=period, filed=filed, primary_doc="")
    filings = [f("2026-06-30", "2026-08-14"), f("2026-03-31", "2026-06-01"),   # amendment of Q1
               f("2026-03-31", "2026-05-15"), f("2025-12-31", "2026-02-17")]
    cur, pri = pick_filing_pair(filings)
    assert (cur.period, pri.period, pri.filed) == ("2026-06-30", "2026-03-31", "2026-06-01")
    cur, pri = pick_filing_pair(filings, "2026-03-31")
    assert (cur.period, pri.period) == ("2026-03-31", "2025-12-31")   # not Q1 vs its amendment
    for bad in ("2024-06-30", "2025-12-31"):                       # unknown / nothing earlier
        try:
            pick_filing_pair(filings, bad)
            raise AssertionError(f"expected an error for {bad}")
        except RuntimeError:
            pass
    print("  pick_filing_pair: PASS")


def test_has_newer_results():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "results" / "0001_2026-06-30").mkdir(parents=True)
        (root / "results" / "0002_2027-03-31").mkdir(parents=True)        # other CIK
        assert run_store.has_newer_results("0001", "2026-03-31", root)
        assert not run_store.has_newer_results("0001", "2026-06-30", root)
        assert not run_store.has_newer_results("0001", "2026-09-30", root)
    print("  has_newer_results: PASS")


if __name__ == "__main__":
    print("Running tests...")
    test_parse()
    test_compare()
    test_duplicate_cusip_rows_are_summed()
    test_name_fallback_does_not_match_across_option_types()
    test_top_movers_rank_by_shares_not_value()
    test_decrease_is_computed_from_prior_filing()
    test_options_ranked_separately_from_equity()
    test_unchanged_share_count_is_not_an_increase()
    test_equity_thresholds_and_pct_ranking()
    test_lookup_tickers_with_mocked_openfigi()
    test_same_period_reuses_store_without_lookup()
    test_only_missing_cusips_are_looked_up()
    test_new_period_does_fresh_lookup()
    test_failed_lookup_is_flagged_and_not_recorded_as_not_found()
    test_commit_run_commits_only_run_files()
    test_readme_latest_results_section()
    test_detail_rows_security_type_and_tickers()
    test_pick_filing_pair()
    test_has_newer_results()
    print("\nAll tests passed.")
