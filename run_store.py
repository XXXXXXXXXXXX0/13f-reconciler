"""
Per-run storage in the repo: a ticker store per filing period, the run's CSVs
under results/, and a commit + push of exactly those files.
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import reconciler_core as rc

REPO_ROOT = Path(__file__).resolve().parent


def ticker_store_path(cik: str, period: str, root: Path = REPO_ROOT) -> Path:
    return root / "tickers" / f"{cik}_{period}.json"


def results_dir(cik: str, period: str, root: Path = REPO_ROOT) -> Path:
    return root / "results" / f"{cik}_{period}"


# ---------------------------------------------------------------------------
# Ticker store
# ---------------------------------------------------------------------------

@dataclass
class TickerResolution:
    tickers: dict           # CUSIP -> ticker for every CUSIP asked about that has one
    store: dict             # store content to write once the run succeeds
    looked_up: list         # CUSIPs sent to OpenFIGI this run
    failed: bool            # lookup errored; do not save or commit this run


def load_ticker_store(path: Path) -> dict:
    """Read a period's store, or an empty one if this period has none yet."""
    if not path.exists():
        return {"tickers": {}, "not_found": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"tickers": dict(data.get("tickers", {})), "not_found": list(data.get("not_found", []))}


def resolve_tickers(cusips: list[str], cik: str, period: str, root: Path = REPO_ROOT,
                    lookup: Callable[[list[str]], rc.TickerLookup] = rc.lookup_tickers
                    ) -> TickerResolution:
    """
    Reuse the store for this CIK + period; ask OpenFIGI only for CUSIPs it has
    never answered for. A new period has its own (empty) file, so its CUSIPs
    are all looked up fresh. Nothing is written here.
    """
    stored = load_ticker_store(ticker_store_path(cik, period, root))
    tickers, not_found = stored["tickers"], set(stored["not_found"])
    wanted = list(dict.fromkeys(c.strip().upper() for c in cusips if c.strip()))
    missing = [c for c in wanted if c not in tickers and c not in not_found]

    failed = False
    if missing:
        result = lookup(missing)
        tickers.update(result.found)
        not_found |= result.not_found
        failed = result.failed

    store = {"cik": cik, "period": period,
             "tickers": dict(sorted(tickers.items())), "not_found": sorted(not_found)}
    return TickerResolution(tickers={c: tickers[c] for c in wanted if c in tickers},
                            store=store, looked_up=missing, failed=failed)


def write_json(path: Path, data: dict) -> None:
    """Write via a temp file so a crash never leaves a half-written store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Commit + push
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, check=check,
                          capture_output=True, text=True)


def commit_run(paths: list[Path], message: str, root: Path = REPO_ROOT,
               push: bool = True, sleep: Callable[[float], None] = time.sleep) -> str:
    """
    Commit exactly `paths` (nothing else that happens to be staged), then push
    the current branch. Returns "committed", "pushed" or "unchanged".
    """
    rel = [str(p.resolve().relative_to(root.resolve())) for p in paths]
    _git(root, "add", "--", *rel)
    if _git(root, "diff", "--cached", "--quiet", "--", *rel, check=False).returncode == 0:
        return "unchanged"
    _git(root, "commit", "-m", message, "--", *rel)
    if not push:
        return "committed"

    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == "HEAD":
        raise RuntimeError("Committed, but not pushed: HEAD is detached (no branch to push).")
    for wait in (2, 4, 8, 16, None):        # retry network failures with backoff
        res = _git(root, "push", "-u", "origin", branch, check=False)
        if res.returncode == 0:
            return "pushed"
        if wait is None:
            raise RuntimeError(f"Committed, but push to origin/{branch} failed:\n{res.stderr.strip()}")
        sleep(wait)
    return "committed"  # unreachable
