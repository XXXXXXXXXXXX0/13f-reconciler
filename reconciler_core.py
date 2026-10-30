"""
Core parsing and comparison logic for the 13F reconciler.
No I/O — pure functions operating on data structures.
"""

import re
import time
import json
from dataclasses import dataclass, replace
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

EDGAR_BASE = "https://data.sec.gov"
ARCHIVE_BASE = "https://www.sec.gov"  # filing documents live here, not on data.sec.gov
USER_AGENT = "13F-Reconciler angelagr2@aol.com"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html, application/xml, */*",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, delay: float = 0.6) -> bytes:
    """Fetch a URL respecting SEC's rate limit (max 10 req/s)."""
    time.sleep(delay)
    # Override Host header per-request so it matches the target domain
    req = Request(url, headers={**HEADERS, "Host": url.split("/")[2]})
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read()
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e


def _get_json(url: str) -> dict:
    return json.loads(_get(url))


def _get_text(url: str) -> str:
    return _get(url).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

def resolve_cik(cik: Optional[str] = None, name: Optional[str] = None) -> str:
    """Return zero-padded 10-digit CIK string."""
    if cik:
        raw = re.sub(r"[^\d]", "", cik)
        return raw.zfill(10)
    if not name:
        raise ValueError("Provide either cik or name")
    url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?company={quote(name)}&CIK=&type=13F-HR&dateb=&owner=include"
        f"&count=10&search_text=&action=getcompany&output=atom"
    )
    text = _get_text(url)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(text)
    for entry in root.findall("a:entry", ns):
        cik_elem = entry.find("a:id", ns)
        if cik_elem is not None:
            m = re.search(r"CIK=(\d+)", cik_elem.text or "")
            if m:
                return m.group(1).zfill(10)
    raise RuntimeError(f"Could not find CIK for name: {name!r}")


# ---------------------------------------------------------------------------
# Filing discovery
# ---------------------------------------------------------------------------

@dataclass
class FilingMeta:
    accession: str      # e.g. "0001067983-24-000010"
    period: str         # "YYYY-MM-DD"
    filed: str          # "YYYY-MM-DD"
    primary_doc: str    # full URL to primary document


def get_13f_filings(cik: str, max_filings: int = 5) -> list[FilingMeta]:
    """Return the most recent 13F-HR filings for a CIK, newest first."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    data = _get_json(url)

    results: list[FilingMeta] = []
    for page_key in ["recent", None]:
        if page_key:
            filings_raw = data.get("filings", {}).get(page_key, {})
        else:
            break
        _collect_filings(filings_raw, cik, results, max_filings)
        if len(results) >= max_filings:
            break

    # Fetch additional submission pages if needed
    for file_ref in data.get("filings", {}).get("files", []):
        if len(results) >= max_filings:
            break
        extra_url = f"{EDGAR_BASE}/submissions/{file_ref['name']}"
        extra = _get_json(extra_url)
        _collect_filings(extra, cik, results, max_filings)

    if len(results) < 2:
        raise RuntimeError(
            f"Found only {len(results)} 13F-HR filing(s) for CIK {cik}. "
            "Need at least 2 to compare quarters."
        )
    return results[:max_filings]


def _collect_filings(raw: dict, cik: str, out: list, limit: int) -> None:
    forms = raw.get("form", [])
    accessions = raw.get("accessionNumber", [])
    filed_dates = raw.get("filingDate", [])
    periods = raw.get("reportDate", [])
    primary_docs = raw.get("primaryDocument", [])

    for i, form in enumerate(forms):
        if len(out) >= limit:
            return
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        acc_nodash = accessions[i].replace("-", "")
        primary = primary_docs[i] if i < len(primary_docs) else ""
        doc_url = (
            f"{ARCHIVE_BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{primary}"
        )
        out.append(FilingMeta(
            accession=accessions[i],
            period=periods[i] if i < len(periods) else "",
            filed=filed_dates[i] if i < len(filed_dates) else "",
            primary_doc=doc_url,
        ))


# ---------------------------------------------------------------------------
# Holding data model
# ---------------------------------------------------------------------------

@dataclass
class Holding:
    issuer_name: str
    cusip: str
    ticker: str
    option_type: str          # "Call", "Put", or ""
    shares: int
    share_type: str           # "SH" (shares) or "PRN" (principal amount, not shares)
    market_value: int         # whole US dollars as reported (since 2023)
    investment_discretion: str
    voting_authority_sole: int
    voting_authority_shared: int
    voting_authority_none: int


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    return re.sub(r"\{[^}]+\}", "", tag)


def _find_text(elem, *names: str) -> str:
    for name in names:
        for child in elem:
            if _strip_ns(child.tag).lower() == name.lower():
                return (child.text or "").strip()
    return ""


def _find_elem(elem, *names: str):
    for name in names:
        for child in elem:
            if _strip_ns(child.tag).lower() == name.lower():
                return child
    return None


def _safe_int(s: str) -> int:
    try:
        return int(re.sub(r"[^\d]", "", s))
    except ValueError:
        return 0


def parse_info_table_xml(xml_text: str) -> list[Holding]:
    """Parse a 13F information table XML string into a list of Holdings."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        clean = re.sub(r"[^\x09\x0A\x0D\x20-퟿-�]", "", xml_text)
        root = ET.fromstring(clean.encode("utf-8"))

    holdings: list[Holding] = []
    for entry in root:
        if _strip_ns(entry.tag).lower() != "infotable":
            continue

        ssh_elem = _find_elem(entry, "shrsOrPrnAmt")
        shares = 0
        share_type = "SH"
        if ssh_elem is not None:
            shares = _safe_int(_find_text(ssh_elem, "sshPrnamt"))
            share_type = _find_text(ssh_elem, "sshPrnamtType").upper() or "SH"

        va_elem = _find_elem(entry, "votingAuthority")
        va_sole = va_shared = va_none = 0
        if va_elem is not None:
            va_sole = _safe_int(_find_text(va_elem, "Sole"))
            va_shared = _safe_int(_find_text(va_elem, "Shared"))
            va_none = _safe_int(_find_text(va_elem, "None"))

        option_raw = _find_text(entry, "putCall")
        option_type = option_raw.capitalize() if option_raw else ""

        holdings.append(Holding(
            issuer_name=_find_text(entry, "nameOfIssuer"),
            cusip=_find_text(entry, "cusip"),
            ticker="",
            option_type=option_type,
            shares=shares,
            share_type=share_type,
            market_value=_safe_int(_find_text(entry, "value")),
            investment_discretion=_find_text(entry, "investmentDiscretion"),
            voting_authority_sole=va_sole,
            voting_authority_shared=va_shared,
            voting_authority_none=va_none,
        ))

    return holdings


# ---------------------------------------------------------------------------
# Filing document retrieval
# ---------------------------------------------------------------------------

def _find_info_table_url(cik: str, filing: FilingMeta) -> str:
    """Locate the information table XML document URL within a filing."""
    acc_nodash = filing.accession.replace("-", "")
    base = f"{ARCHIVE_BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}"
    try:
        idx = _get_json(f"{base}/index.json")
    except Exception:
        return filing.primary_doc

    names = [item.get("name", "") for item in idx.get("directory", {}).get("item", [])]
    xml_names = [n for n in names if n.lower().endswith(".xml")]

    # Prefer the document named like an information table
    for name in xml_names:
        if "infotable" in name.lower() or "information" in name.lower():
            return f"{base}/{name}"

    # Fall back: any XML file other than the primary doc
    for name in xml_names:
        if name.lower() != "primary_doc.xml":
            return f"{base}/{name}"

    return filing.primary_doc


def fetch_holdings(cik: str, filing: FilingMeta) -> list[Holding]:
    """Download and parse the 13F information table for one filing."""
    url = _find_info_table_url(cik, filing)
    text = _get_text(url)

    # If we got HTML, look for an embedded XML link
    if not text.lstrip().startswith("<") or text.lstrip().startswith("<!"):
        m = re.search(r'href="([^"]*infotable[^"]*\.xml)"', text, re.IGNORECASE)
        if not m:
            m = re.search(r'href="([^"]*\.xml)"', text, re.IGNORECASE)
        if m:
            xml_rel = m.group(1)
            if not xml_rel.startswith("http"):
                acc_nodash = filing.accession.replace("-", "")
                xml_rel = (
                    f"{ARCHIVE_BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{xml_rel}"
                )
            text = _get_text(xml_rel)

    if not text.lstrip().startswith("<"):
        raise RuntimeError(f"Could not retrieve XML information table from {url}")

    return parse_info_table_xml(text)


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

@dataclass
class PositionChange:
    category: str           # "New", "Closed", "Changed"
    direction: str          # "Increase", "Decrease", or "" for New/Closed
    issuer_name_current: str
    issuer_name_prior: str
    cusip: str
    ticker: str
    option_type: str
    share_type: str         # "SH" or "PRN"; PRN amounts are not share counts
    prior_shares: int
    current_shares: int
    share_change: int
    prior_market_value: int
    current_market_value: int
    market_value_change: int
    prior_period: str
    prior_filed: str
    current_period: str
    current_filed: str
    note: str               # e.g. "Name changed", "CUSIP changed"


def _holding_key(h: Holding) -> tuple[str, str, str]:
    """(CUSIP, option_type, share_type) — stable across name/ticker changes."""
    return (h.cusip.upper().strip(), h.option_type.lower(), h.share_type)


def _name_key(h: Holding) -> tuple[str, str, str]:
    """Issuer name plus option/share type, so a put never matches the common stock."""
    return (re.sub(r"[^a-z0-9]", "", h.issuer_name.lower()), h.option_type.lower(), h.share_type)


def aggregate_holdings(holdings: list[Holding]) -> list[Holding]:
    """
    Sum rows that share a (CUSIP, option_type, share_type) key.

    A 13F lists one row per sub-manager / discretion type, so the same CUSIP
    commonly appears on several rows. Comparing quarters on single rows would
    silently drop all but one of them.
    """
    merged: dict[tuple, Holding] = {}
    for h in holdings:
        key = _holding_key(h)
        if key not in merged:
            merged[key] = replace(h)
            continue
        m = merged[key]
        m.shares += h.shares
        m.market_value += h.market_value
        m.voting_authority_sole += h.voting_authority_sole
        m.voting_authority_shared += h.voting_authority_shared
        m.voting_authority_none += h.voting_authority_none
    return list(merged.values())


def compare_holdings(
    prior: list[Holding],
    current: list[Holding],
    prior_filing: FilingMeta,
    current_filing: FilingMeta,
) -> list[PositionChange]:
    """
    Compare two quarters of holdings and return classified position changes,
    sorted by absolute share count change descending.
    """
    prior = aggregate_holdings(prior)
    current = aggregate_holdings(current)
    prior_map: dict[tuple, Holding] = {_holding_key(h): h for h in prior}
    current_map: dict[tuple, Holding] = {_holding_key(h): h for h in current}
    prior_name_map: dict[tuple, Holding] = {_name_key(h): h for h in prior}
    current_name_map: dict[tuple, Holding] = {_name_key(h): h for h in current}

    results: list[PositionChange] = []
    matched_prior_keys: set[tuple] = set()

    def _make_change(cat, direction, cur, pri, note) -> PositionChange:
        share_delta = (cur.shares if cur else 0) - (pri.shares if pri else 0)
        mv_delta = (cur.market_value if cur else 0) - (pri.market_value if pri else 0)
        return PositionChange(
            category=cat,
            direction=direction,
            issuer_name_current=cur.issuer_name if cur else "",
            issuer_name_prior=pri.issuer_name if pri else "",
            cusip=cur.cusip if cur else (pri.cusip if pri else ""),
            ticker=cur.ticker if cur else (pri.ticker if pri else ""),
            option_type=cur.option_type if cur else (pri.option_type if pri else ""),
            share_type=cur.share_type if cur else (pri.share_type if pri else "SH"),
            prior_shares=pri.shares if pri else 0,
            current_shares=cur.shares if cur else 0,
            share_change=share_delta,
            prior_market_value=pri.market_value if pri else 0,
            current_market_value=cur.market_value if cur else 0,
            market_value_change=mv_delta,
            prior_period=prior_filing.period,
            prior_filed=prior_filing.filed,
            current_period=current_filing.period,
            current_filed=current_filing.filed,
            note=note,
        )

    for key, cur in current_map.items():
        note = ""
        pri = None

        if key in prior_map:
            pri = prior_map[key]
            matched_prior_keys.add(key)
            if pri.issuer_name != cur.issuer_name:
                note = "Name changed"
        else:
            # Name-based fallback for CUSIP reissuance
            nk = _name_key(cur)
            if nk in prior_name_map and _holding_key(prior_name_map[nk]) not in matched_prior_keys:
                pri = prior_name_map[nk]
                matched_prior_keys.add(_holding_key(pri))
                note = "CUSIP changed"

        if pri is None:
            results.append(_make_change("New", "", cur, None, ""))
            continue

        share_delta = cur.shares - pri.shares
        mv_delta = cur.market_value - pri.market_value
        if share_delta == 0 and mv_delta == 0 and not note:
            continue  # truly unchanged; exclude from output

        # No size threshold: any change in share count counts. A position whose
        # count is unchanged (price move only) is "No Change", not an increase.
        direction = ("Increase" if share_delta > 0
                     else "Decrease" if share_delta < 0 else "No Change")
        results.append(_make_change("Changed", direction, cur, pri, note))

    # Closed: in prior but not matched by CUSIP or name
    for pk, pri in prior_map.items():
        if pk in matched_prior_keys:
            continue
        if _name_key(pri) in current_name_map:
            continue  # matched via name already
        results.append(_make_change("Closed", "", None, pri, ""))

    results.sort(key=lambda x: abs(x.share_change), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Largest movers (ranked by share count)
# ---------------------------------------------------------------------------

TOP_SECTIONS = (
    ("Equity", "New"), ("Equity", "Closed"), ("Equity", "Increase"), ("Equity", "Decrease"),
    ("Call", "Increase"), ("Call", "Decrease"),
    ("Put", "Increase"), ("Put", "Decrease"),
    ("Bond", "New"),
)


def asset_class(c: PositionChange) -> str:
    """Equity, Call, Put, or Bond (PRN rows report principal, not shares)."""
    if c.share_type == "PRN":
        return "Bond"
    return c.option_type or "Equity"


def top_movers(changes: list[PositionChange], n: int = 10) -> dict[tuple, list[PositionChange]]:
    """
    Top-n positions per (asset class, section), ranked by size, never by value.

    Equity, calls, puts and bonds are ranked in separate tables; they were
    never summed together (the matching key includes put/call and SH/PRN).
    A change is current minus prior for the same key, since filings only
    report positive counts. For calls and puts, Increase includes newly
    opened positions and Decrease includes fully closed ones. Bonds rank by
    principal amount.
    """
    def wanted(c: PositionChange, cls: str, section: str) -> bool:
        if asset_class(c) != cls:
            return False
        if section in ("New", "Closed"):
            return c.category == section
        moved = c.share_change > 0 if section == "Increase" else c.share_change < 0
        return moved and (cls != "Equity" or c.category == "Changed")

    return {
        (cls, section): sorted(
            (c for c in changes if wanted(c, cls, section)),
            key=lambda c: abs(c.share_change), reverse=True,
        )[:n]
        for cls, section in TOP_SECTIONS
    }


# ---------------------------------------------------------------------------
# CUSIP -> ticker (13F filings carry no tickers)
# ---------------------------------------------------------------------------

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


def _post_json(url: str, payload: list, headers: dict) -> list:
    req = Request(url, data=json.dumps(payload).encode(), method="POST",
                  headers={"Content-Type": "application/json", **headers})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _pick_ticker(matches: list[dict]) -> str:
    """Prefer the US composite listing, else the first match that has a ticker."""
    with_ticker = [m for m in matches if m.get("ticker")]
    for m in with_ticker:
        if m.get("exchCode") == "US":
            return m["ticker"]
    return with_ticker[0]["ticker"] if with_ticker else ""


def lookup_tickers(cusips: list[str], api_key: Optional[str] = None,
                   post=_post_json, sleep=time.sleep) -> dict[str, str]:
    """
    Map CUSIPs to tickers with the OpenFIGI API (free; set OPENFIGI_API_KEY for
    higher limits). Returns only the CUSIPs it resolved; never raises, so a
    blocked or rate-limited lookup just leaves tickers blank.
    """
    unique = list(dict.fromkeys(c.strip().upper() for c in cusips if c.strip()))
    batch = 100 if api_key else 10          # per-request job limit
    pause = 0.3 if api_key else 2.6         # 25 req/min without a key
    headers = {"X-OPENFIGI-APIKEY": api_key} if api_key else {}
    found: dict[str, str] = {}
    for i in range(0, len(unique), batch):
        chunk = unique[i:i + batch]
        jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in chunk]
        try:
            try:
                results = post(OPENFIGI_URL, jobs, headers)
            except HTTPError as e:
                if e.code != 429:
                    raise
                sleep(30)
                results = post(OPENFIGI_URL, jobs, headers)
        except (HTTPError, URLError, OSError, ValueError) as e:
            print(f"  WARNING: ticker lookup failed ({e}); tickers left blank.")
            return found
        for cusip, res in zip(chunk, results):
            ticker = _pick_ticker(res.get("data", [])) if isinstance(res, dict) else ""
            if ticker:
                found[cusip] = ticker
        sleep(pause)
    return found
