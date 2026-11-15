"""Fetch the documents behind the "Ask NASA's records" corpus, untouched, into data/raw/docs/.

1. pages: the official challenge resources (NASA web pages, and a PDF linked from the
   Researcher's Guide page if there is one).
2. ntrs:  for every publication title in the PSI records, one search on NASA's public
   NTRS API (https://ntrs.nasa.gov/api). The raw search response is saved; matching
   and rights decisions are made later, in src/build_corpus.py.

Every file is listed in data/raw/docs/manifest.csv with its URL, access time and
sha256. Requests are sequential with a pause. A file already saved is not fetched again.

Run:  python src/fetch_docs.py pages
      python src/fetch_docs.py ntrs
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "raw" / "docs"
MANIFEST = DOCS / "manifest.csv"
RECORDS = ROOT / "data" / "raw" / "psi" / "investigations"
FIELDS = ["kind", "doc_id", "url", "saved_as", "accessed_utc", "bytes", "sha256", "note"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; student research script; sequential requests)"}
PAUSE_S = 1.0
MAX_BYTES = 40 * 1024 * 1024

PAGES = {
    "nasa-researchers-guide-combustion": "https://www.nasa.gov/missions/station/a-researchers-guide-to-combustion-science/",
    "nasa-glenn-combustion-science": "https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/",
    "nasa-sma-apollo-1": "https://sma.nasa.gov/sma-disciplines/accllp/apollo-1",
    "nasa-sma-apollo-13": "https://sma.nasa.gov/sma-disciplines/accllp/apollo-13",
    "nasa-history-mir-fire": "https://www.nasa.gov/history/25-years-ago-fire-aboard-space-station-mir/",
    "nasa-spinoff-9407": "https://spinoff.nasa.gov/node/9407",
}
NTRS_SEARCH = "https://ntrs.nasa.gov/api/citations/search"
NTRS_RECORD = "https://ntrs.nasa.gov/api/citations/{}"
FLEX_REPORT_ID = 20150023456  # NASA/TP-2015-216046


def manifest_rows() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def record(rows: list[dict], kind: str, doc_id: str, url: str, path: Path | None, note: str = "") -> None:
    data = path.read_bytes() if path else b""
    rows[:] = [r for r in rows if not (r["kind"] == kind and r["doc_id"] == doc_id)]
    rows.append({"kind": kind, "doc_id": doc_id, "url": url,
                 "saved_as": path.relative_to(ROOT).as_posix() if path else "",
                 "accessed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "bytes": len(data) if path else "", "sha256": hashlib.sha256(data).hexdigest() if path else "",
                 "note": note})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def fetch(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[bytes, str]:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            length = int(r.headers.get("Content-Length") or 0)
            if length > MAX_BYTES:
                raise ValueError(f"too large: {length} bytes")
            return r.read(MAX_BYTES + 1), r.headers.get("Content-Type", "")
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e) or data is not None:
            raise
        # The Windows certificate store lacks an intermediate certificate for this host.
        # Retry with the certifi bundle; the certificate is still verified.
        import requests
        r = requests.get(url, headers={**UA, **(headers or {})}, timeout=60, verify=True)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "")


def pages() -> None:
    rows = manifest_rows()
    have = {r["doc_id"] for r in rows if r["saved_as"]}
    for doc_id, url in PAGES.items():
        if doc_id in have:
            print("have   ", doc_id)
            continue
        path = DOCS / "pages" / f"{doc_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            body, ctype = fetch(url)
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            record(rows, "nasa_page", doc_id, url, None, f"not fetched: {e}")
            print("FAILED ", doc_id, e)
            continue
        path.write_bytes(body)
        record(rows, "nasa_page", doc_id, url, path, ctype)
        print("saved  ", doc_id, len(body), ctype)
        time.sleep(PAUSE_S)
    # a PDF linked from the Researcher's Guide page, if any
    guide = DOCS / "pages" / "nasa-researchers-guide-combustion.html"
    if guide.exists() and "nasa-researchers-guide-combustion-pdf" not in have:
        links = re.findall(r'href="([^"]+\.pdf[^"]*)"', guide.read_text(encoding="utf-8", errors="replace"))
        links = list(dict.fromkeys(links))
        print("PDF links on the guide page:", links)
        for url in links[:1]:
            path = DOCS / "pages" / "nasa-researchers-guide-combustion.pdf"
            try:
                body, ctype = fetch(url)
                if len(body) > MAX_BYTES:
                    raise ValueError("too large")
            except (urllib.error.URLError, ValueError, TimeoutError) as e:
                record(rows, "nasa_report", "nasa-researchers-guide-combustion-pdf", url, None, f"not fetched: {e}")
                print("FAILED  guide pdf", e)
                continue
            path.write_bytes(body)
            record(rows, "nasa_report", "nasa-researchers-guide-combustion-pdf", url, path, ctype)
            print("saved   guide pdf", len(body))


def norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def publication_titles() -> dict[str, str]:
    """normalised title -> title as printed, for every publication in the 24 PSI records."""
    out: dict[str, str] = {}
    for path in sorted(RECORDS.glob("PSI-*.json")):
        for p in json.loads(path.read_text(encoding="utf-8")).get("publications") or []:
            t = (p.get("title") or "").strip()
            if t and norm(t):
                out.setdefault(norm(t), t)
    return out


def ntrs() -> None:
    rows = manifest_rows()
    have = {r["doc_id"] for r in rows if r["kind"].startswith("ntrs")}
    out_dir = DOCS / "ntrs"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_id = f"ntrs-{FLEX_REPORT_ID}"
    if doc_id not in have:
        url = NTRS_RECORD.format(FLEX_REPORT_ID)
        body, _ = fetch(url)
        path = out_dir / f"record_{FLEX_REPORT_ID}.json"
        path.write_bytes(body)
        record(rows, "ntrs_record", doc_id, url, path, "NASA/TP-2015-216046, fetched by id")
        time.sleep(PAUSE_S)
    titles = publication_titles()
    print(len(titles), "distinct publication titles")
    for k, (key, title) in enumerate(titles.items(), 1):
        doc_id = "search-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        if doc_id in have:
            continue
        body_out = json.dumps({"q": title, "page": {"size": 3, "from": 0}}).encode()
        path = out_dir / "search" / f"{doc_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in (1, 2):
            try:
                body, _ = fetch(NTRS_SEARCH, data=body_out, headers={"Content-Type": "application/json"})
                path.write_bytes(body)
                record(rows, "ntrs_search", doc_id, NTRS_SEARCH, path, f"POST q = {title}")
                break
            except (urllib.error.URLError, ValueError, TimeoutError) as e:
                if attempt == 2:
                    record(rows, "ntrs_search", doc_id, NTRS_SEARCH, None, f"not fetched: {e}; POST q = {title}")
                time.sleep(5)
        if k % 25 == 0:
            print(k, "of", len(titles), flush=True)
        time.sleep(PAUSE_S)
    print("done")


if __name__ == "__main__":
    {"pages": pages, "ntrs": ntrs}[sys.argv[1]]()
