"""
Unit tests for 13F reconciler logic using synthetic 13F XML data.
Run: python test_reconciler.py
"""

import sys
import textwrap
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
    aggregate_holdings, top_movers, lookup_tickers,
)


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
    assert [c.issuer_name_current for c in top["New"]] == ["NEW BIG", "NEW SMALL"]
    assert [c.issuer_name_prior for c in top["Closed"]] == ["GONE BIG", "GONE SMALL"]
    assert [c.issuer_name_current for c in top["Increase"]] == ["MANY SHARES", "BIG VALUE"]
    assert top["Decrease"] == []
    assert all(c.share_type == "SH" for rows in top.values() for c in rows)  # PRN excluded
    print("  top_movers by share count: PASS")


def test_decrease_is_computed_from_prior_filing():
    """Filings report positive counts only; a cut shows up as current - prior < 0."""
    changes = compare_holdings([H("CUT", "Z", 1_000)], [H("CUT", "Z", 400)],
                               make_filing("a", "a"), make_filing("b", "b"))
    assert changes[0].share_change == -600 and changes[0].direction == "Decrease"
    assert top_movers(changes)["Decrease"][0].share_change == -600
    print("  decrease computed vs prior: PASS")


def test_lookup_tickers_with_mocked_openfigi():
    calls = []

    def fake_post(url, jobs, headers):
        calls.append(len(jobs))
        out = []
        for j in jobs:
            if j["idValue"] == "AAA":
                out.append({"data": [{"ticker": "AAA.F", "exchCode": "GR"},
                                     {"ticker": "AAA", "exchCode": "US"}]})
            else:
                out.append({"warning": "No identifier found."})
        return out

    got = lookup_tickers(["aaa", "AAA", "BBB"] + [f"X{i}" for i in range(11)],
                         post=fake_post, sleep=lambda s: None)
    assert got == {"AAA": "AAA"}
    assert calls == [10, 3]          # de-duplicated, batched 10 per request without a key

    def boom(url, jobs, headers):
        raise OSError("blocked")
    assert lookup_tickers(["AAA"], post=boom, sleep=lambda s: None) == {}
    print("  lookup_tickers: PASS")


if __name__ == "__main__":
    print("Running tests...")
    test_parse()
    test_compare()
    test_duplicate_cusip_rows_are_summed()
    test_name_fallback_does_not_match_across_option_types()
    test_top_movers_rank_by_shares_not_value()
    test_decrease_is_computed_from_prior_filing()
    test_lookup_tickers_with_mocked_openfigi()
    print("\nAll tests passed.")
