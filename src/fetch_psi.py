"""Fetch NASA PSI metadata for every Combustion Science investigation.

Source: the public JSON API behind https://psi.nasa.gov/physci/repo/search
(found in the page's own script):
  list     GET /geode-py/ws/repo/search?source=psi&type=investigation&from=..&size=..
  record   GET /geode-py/ws/repo/investigations/<PSI-id>
  file     GET /geode-py/ws/studies/<PSI-id>/download?file=<name>&version=<n>&redirect=false
           (returns a short-lived download link for that one file)

Writes, under data/raw/psi/ (never edited afterwards):
  search/page_<n>.json            raw search responses
  investigations/<PSI-id>.json    raw record of each Combustion Science investigation
  tables/<PSI-id>/<file>.csv      its "Experimental table" CSV files, if any, up to 5 MB each
  manifest.csv                    one line per request: URL, access time (UTC), bytes, sha256

Only metadata and experimental-table CSVs are requested: no raw data, images or
video. Requests are sequential with a pause between them. A file that already
exists is not fetched again.

Run from anywhere:  python src/fetch_psi.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "psi"
MANIFEST = OUT / "manifest.csv"
BASE = "https://psi.nasa.gov/geode-py/ws"
RESEARCH_AREA = "Combustion Science"
MAX_TABLE_BYTES = 5 * 1024 * 1024
PAGE_SIZE = 100
PAUSE_S = 1.0
FIELDS = ["kind", "psi_id", "url", "saved_as", "accessed_utc", "bytes", "sha256", "note"]


def get(url: str) -> bytes:
    time.sleep(PAUSE_S)
    req = urllib.request.Request(url, headers={"User-Agent": "python-urllib (research script)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def log(row: dict) -> None:
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def save(kind: str, psi_id: str, url: str, path: Path, fetch_url: str | None = None) -> bytes | None:
    """Fetch `fetch_url or url` and store the bytes untouched. The manifest records `url`."""
    if path.exists():
        print(f"  exists, not fetched again: {path.relative_to(ROOT)}")
        return path.read_bytes()
    data = get(fetch_url or url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    log({"kind": kind, "psi_id": psi_id, "url": url, "saved_as": path.relative_to(ROOT).as_posix(),
         "accessed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    print(f"  saved {path.relative_to(ROOT)} ({len(data)} bytes)")
    return data


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- 1. list every PSI investigation --------------------------------
    hits, page = [], 0
    while True:
        url = f"{BASE}/repo/search?source=psi&type=investigation&from={page * PAGE_SIZE}&size={PAGE_SIZE}"
        body = json.loads(save("search", "", url, OUT / "search" / f"page_{page}.json"))
        hits += body["hits"]["hits"]
        total = body["hits"]["total"]
        total = total["value"] if isinstance(total, dict) else total
        page += 1
        if len(hits) >= total or not body["hits"]["hits"]:
            break
    print(f"PSI lists {total} investigations; {len(hits)} read.")
    areas: dict[str, int] = {}
    for h in hits:
        a = h["_source"].get("Research Area", "")
        areas[a] = areas.get(a, 0) + 1
    print("Research areas:", areas)
    ids = sorted((h["_source"]["Accession"] for h in hits if h["_source"].get("Research Area") == RESEARCH_AREA),
                 key=lambda s: int(s.split("-")[1]))
    print(f"{len(ids)} investigations with Research Area = {RESEARCH_AREA}: {', '.join(ids)}")

    # ---- 2. each record, 3. its experimental-table CSVs -------------------
    for pid in ids:
        print(pid)
        url = f"{BASE}/repo/investigations/{pid}"
        rec = json.loads(save("investigation", pid, url, OUT / "investigations" / f"{pid}.json"))
        for t in rec.get("experimentalTable") or []:
            name, size, version = t.get("file_name", ""), t.get("file_size") or 0, t.get("version")
            target = OUT / "tables" / pid / name
            link_url = (f"{BASE}/studies/{pid}/download?file={urllib.parse.quote(name)}"
                        f"&version={version}&redirect=false")
            if target.exists():
                print(f"  exists, not fetched again: {target.relative_to(ROOT)}")
                continue
            if not name.lower().endswith(".csv"):
                log({"kind": "table_skipped", "psi_id": pid, "url": link_url, "bytes": size,
                     "note": f"not a CSV file: {name}"})
                print(f"  skipped (not CSV): {name}")
                continue
            if size > MAX_TABLE_BYTES:
                log({"kind": "table_skipped", "psi_id": pid, "url": link_url, "bytes": size,
                     "note": f"over 5 MB: {name}"})
                print(f"  skipped (over 5 MB, {size} bytes): {name}")
                continue
            try:
                signed = get(link_url).decode("utf-8").strip()
                if not signed.startswith("https://"):
                    raise ValueError(f"unexpected reply: {signed[:80]}")
                save("experimental_table", pid, link_url, target, fetch_url=signed)
            except Exception as e:  # one failed file must not stop the run
                log({"kind": "table_failed", "psi_id": pid, "url": link_url, "bytes": size,
                     "note": f"{type(e).__name__}: {e}"[:200]})
                print(f"  FAILED {name}: {type(e).__name__}: {e}")
    print(f"\nManifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
