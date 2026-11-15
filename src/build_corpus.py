"""Build the text corpus for the "Ask NASA's records" page.

Sources (all raw files stay untouched in data/raw/):
- psi_record     the 24 PSI records (data/raw/psi/investigations/)
- nasa_page      the challenge's NASA web pages (data/raw/docs/pages/*.html)
- nasa_report    NASA's "Researcher's Guide to Combustion Science" PDF (needs pypdf, a build-time package)
- ntrs_abstract  abstracts of the PSI publications found on NASA's NTRS (data/raw/docs/ntrs/)
- data_card      short passages computed by this script from NASA tables; every number comes from the
                 file named in the passage

Outputs in data/corpus/:
- passages.jsonl   one passage per paragraph
- documents.csv    one row per document: source type, URL, rights basis, whether its text is used
- ntrs_log.csv     one row per publication title looked up on NTRS: matched or skipped, and why

Text is copied word for word. The only changes: HTML tags removed and entities decoded; runs of
whitespace inside a web or PDF paragraph become one space; in the PDF, wrapped lines are joined and the
extraction artefact "• R emoval" (a gap after a bullet's first letter) is closed.

Rights: only NASA-authored or NASA-published text is used. An NTRS abstract is used only when NTRS's own
copyright determination permits public use and the record is not marked as belonging to a publisher;
otherwise only the title and the link are kept. A web page with a copyright notice is title and link only.

A paragraph of a PSI record is one line of the field; lines of a numbered or bulleted list stay with the
line that introduces them.

Run:  python src/build_corpus.py
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

import html_text

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "data" / "raw" / "psi" / "investigations"
DOCS = ROOT / "data" / "raw" / "docs"
DOCS_MANIFEST = DOCS / "manifest.csv"
OUT = ROOT / "data" / "corpus" / "passages.jsonl"
DOCUMENTS = ROOT / "data" / "corpus" / "documents.csv"
NTRS_LOG = ROOT / "data" / "corpus" / "ntrs_log.csv"
CATALOG = ROOT / "data" / "catalog" / "investigations.csv"
UNIFIED = ROOT / "data" / "unified" / "tests_conditions.csv"
FLEX_CLEAN = ROOT / "data" / "clean" / "flex_clean.csv"
PSI_PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{}"
NTRS_PAGE = "https://ntrs.nasa.gov/citations/{}"
FLEX_REPORT_ID = 20150023456

# (key in the PSI record, field name in the corpus, short tag used in passage_id)
FIELDS = [
    ("title", "title", "title"),
    ("proposalTitle", "proposal title", "proposal"),
    ("description", "description", "description"),
    ("objective", "objective", "objective"),
    ("approach", "approach", "approach"),
    ("hypothesis", "hypothesis", "hypothesis"),
    ("researchImpacts", "research impacts", "impacts"),
    ("experimentHardware", "experiment hardware", "hardware"),
]
PUBLICATION = ("publications[].title", "publication title", "pub")

MIN_CHARS = 80            # shorter web/PDF paragraphs are bylines, captions and link lists
TITLE_MATCH = 0.92        # NTRS title similarity needed when the titles are not identical
NTRS_PUBLIC = {"PUBLIC_USE_PERMITTED", "GOV_PUBLIC_USE_PERMITTED"}
PAGE_TITLES = {  # used only if the page gives no <h1>
    "nasa-sma-apollo-1": "Apollo 1 (NASA Safety and Mission Assurance)",
    "nasa-sma-apollo-13": "Apollo 13 (NASA Safety and Mission Assurance)",
}

_TAG = re.compile(r"<[a-zA-Z/][^<>]*>")
_LIST_ITEM = re.compile(r"^\s*(?:\d{1,2}[.)]|[A-Za-z][.)]|[-*•])\s+\S")
_CAPTION = re.compile(r"^(?:(?:Left|Right|Middle|Center|Top|Bottom)\b[^.]{0,30}:|(?:Two|Three|Four|Five) images of\b)")
_COPYRIGHT = re.compile(r"(?i)(©|\bcopyright\s+(?:©|\(c\)|\d{4}))")


def clean(text: str) -> str:
    """Strip HTML tags and decode HTML entities. Nothing else."""
    return html.unescape(_TAG.sub("", text))


def paragraphs(text: str) -> list[str]:
    out: list[str] = []
    for line in clean(text).replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        if out and _LIST_ITEM.match(line):
            out[-1] += "\n" + line.rstrip()
        else:
            out.append(line.strip())
    return out


def norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def psi_number(path: Path) -> int:
    return int(path.stem.split("-")[1])


def passage(passage_id, text, source_type, doc_id, doc_title, section, source_url, psi_ids=(), acronym="",
            investigation="", field="") -> dict:
    psi_ids = sorted(set(psi_ids), key=lambda i: int(i.split("-")[1]))
    return {"passage_id": passage_id, "psi_id": psi_ids[0] if len(psi_ids) == 1 else "", "psi_ids": psi_ids,
            "acronym": acronym, "investigation": investigation, "source_url": source_url,
            "field": field or section, "source_type": source_type, "doc_id": doc_id, "doc_title": doc_title,
            "section": section, "text": text}


# ---------------------------------------------------------------------------
# which investigation does a text name?
# ---------------------------------------------------------------------------
def name_patterns(records: list[dict]) -> list[tuple[re.Pattern, str]]:
    """One pattern per investigation acronym (as PSI prints it), case-sensitive, whole token.
    A longer acronym wins over a shorter one it contains (FLEX-2 over FLEX, SAME-R over SAME)."""
    pats = []
    for rec in records:
        for part in re.split(r"\s*/\s*", (rec.get("investigationAcronym") or "").strip()):
            part = re.sub(r"^ACME\s+", "", part).strip()
            if len(part) >= 3 and part != "ACME":
                pats.append((part, rec["accession"]))
    pats.sort(key=lambda x: -len(x[0]))
    return [(re.compile(r"(?<![A-Za-z0-9-])" + re.escape(a) + r"(?![A-Za-z0-9]|-[A-Za-z0-9])"), pid) for a, pid in pats]


def named_investigations(text: str, pats) -> list[str]:
    found, rest = [], text
    for pat, pid in pats:
        if pat.search(rest):
            found.append(pid)
            rest = pat.sub(" ", rest)
    return found


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def load_records() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS.glob("PSI-*.json"), key=psi_number)]


def psi_passages(records: list[dict]) -> tuple[list[dict], list[dict], dict]:
    passages, docs, found = [], [], {}
    for rec in records:
        psi_id = rec["accession"]
        title = (rec.get("title") or "").strip()
        base = dict(source_type="psi_record", doc_id=psi_id, doc_title=title, source_url=PSI_PAGE.format(psi_id),
                    psi_ids=[psi_id], acronym=(rec.get("investigationAcronym") or "").strip(), investigation=title)
        n0 = len(passages)
        for key, name, tag in FIELDS:
            value = rec.get(key)
            paras = paragraphs(value) if isinstance(value, str) else []
            found.setdefault(name, {"key": key, "records": 0, "passages": 0})
            found[name]["records"] += bool(paras)
            found[name]["passages"] += len(paras)
            for n, p in enumerate(paras, 1):
                passages.append(passage(f"{psi_id}-{tag}-{n}", p, section=name, **base))
        key, name, tag = PUBLICATION
        titles = [(n, clean(p.get("title") or "").strip()) for n, p in enumerate(rec.get("publications") or [], 1)]
        titles = [(n, t) for n, t in titles if t]
        found.setdefault(name, {"key": key, "records": 0, "passages": 0})
        found[name]["records"] += bool(titles)
        found[name]["passages"] += len(titles)
        for n, t in titles:
            passages.append(passage(f"{psi_id}-{tag}-{n}", t, section=name, **base))
        docs.append({"doc_id": psi_id, "source_type": "psi_record", "title": title, "url": PSI_PAGE.format(psi_id),
                     "rights_basis": f"NASA PSI record; license stated by PSI: {rec.get('licenseIdentifier') or 'not stated'}",
                     "text_used": "yes", "passages": len(passages) - n0, "psi_ids": psi_id, "note": ""})
    return passages, docs, found


def manifest() -> list[dict]:
    if not DOCS_MANIFEST.exists():
        return []
    with DOCS_MANIFEST.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def page_passages(pats, seen: set[str]) -> tuple[list[dict], list[dict]]:
    passages, docs = [], []
    for row in manifest():
        if row["kind"] != "nasa_page":
            continue
        doc = {"doc_id": row["doc_id"], "source_type": "nasa_page", "title": "", "url": row["url"], "rights_basis": "",
               "text_used": "no", "passages": 0, "psi_ids": "", "note": ""}
        docs.append(doc)
        if not row["saved_as"]:
            doc.update(rights_basis="not fetched", note=row["note"], title=PAGE_TITLES.get(row["doc_id"], row["doc_id"]))
            continue
        raw = (ROOT / row["saved_as"]).read_text(encoding="utf-8", errors="replace")
        title, paras = html_text.paragraphs(raw)
        doc["title"] = title or PAGE_TITLES.get(row["doc_id"], row["doc_id"])
        body = [(h, t) for h, t in paras if len(t) >= MIN_CHARS and not _CAPTION.match(t)]  # no bylines, no image captions
        if any(_COPYRIGHT.search(t) for _, t in paras):
            doc["rights_basis"] = "page carries a copyright notice: title and link only"
            continue
        doc["rights_basis"] = "NASA-published web page (" + row["url"].split("/")[2] + "); no copyright notice in its text"
        named: set[str] = set()
        for heading, text in body:
            if text in seen:  # the same paragraph repeated on this or another page
                continue
            seen.add(text)
            ids = named_investigations(heading + " " + text, pats)
            named.update(ids)
            passages.append(passage(f"{row['doc_id']}-{len([p for p in passages if p['doc_id'] == row['doc_id']]) + 1}",
                                    text, "nasa_page", row["doc_id"], doc["title"], heading, row["url"], ids))
        doc.update(text_used="yes", passages=sum(p["doc_id"] == row["doc_id"] for p in passages),
                   psi_ids=" ".join(sorted(named, key=lambda i: int(i.split("-")[1]))))
    return passages, docs


def pdf_paragraphs(path: Path) -> list[tuple[int, str, str]]:
    """(page number, section heading, paragraph). A line that ends with a space is a wrapped line;
    a line that does not ends its paragraph. A short paragraph without a full stop is a heading."""
    from pypdf import PdfReader  # build-time only (requirements-dev.txt)

    out, heading = [], ""
    for n, page in enumerate(PdfReader(str(path)).pages, 1):
        buf: list[str] = []
        first_on_page = True
        for line in (page.extract_text() or "").split("\n") + [""]:
            if line.strip().isdigit():  # page number
                continue
            if line.strip():
                buf.append(line.strip())
            if buf and not line.endswith(" "):
                text = re.sub(r"\s+", " ", " ".join(buf))
                text = re.sub(r"•\s+([A-Z]) (?=[a-z])", "• \\g<1>", text)  # "• R emoval" -> "• Removal"
                buf = []
                first, first_on_page = first_on_page, False
                if len(text) < 70 and not text.endswith((".", ":", ";", ",")) and len(text.split()) <= 9:
                    heading = text
                elif out and out[-1][0] == n and (text.startswith("•") or out[-1][2].endswith(":")):
                    out[-1] = (n, out[-1][1], out[-1][2] + " " + text)  # a list stays with its lead-in
                elif (out and first and out[-1][0] == n - 1 and text[:1].islower()
                      and not out[-1][2].endswith((".", "?", "!", ")", ":"))):
                    out[-1] = (n - 1, out[-1][1], out[-1][2] + " " + text)  # a sentence that runs over the page break
                else:
                    out.append((n, heading, text))
    return out


def report_passages(pats, seen: set[str]) -> tuple[list[dict], list[dict]]:
    passages, docs = [], []
    for row in manifest():
        if row["kind"] != "nasa_report":
            continue
        doc = {"doc_id": row["doc_id"], "source_type": "nasa_report",
               "title": "A Researcher's Guide to: Combustion Science (NASA NP-2015-10-034-JSC)", "url": row["url"],
               "rights_basis": "NASA publication NP-2015-10-034-JSC, published on nasa.gov", "text_used": "no",
               "passages": 0, "psi_ids": "", "note": row["note"] if not row["saved_as"] else ""}
        docs.append(doc)
        if not row["saved_as"]:
            continue
        named: set[str] = set()
        for page, heading, text in pdf_paragraphs(ROOT / row["saved_as"]):
            if page <= 2 or len(text) < MIN_CHARS or text in seen or _COPYRIGHT.search(text):  # pages 1-2: cover and credits
                continue
            seen.add(text)
            ids = named_investigations(heading + " " + text, pats)
            named.update(ids)
            passages.append(passage(f"{row['doc_id']}-{len(passages) + 1}", text, "nasa_report", row["doc_id"],
                                    doc["title"], f"{heading} (page {page})" if heading else f"page {page}",
                                    row["url"], ids))
        doc.update(text_used="yes", passages=len(passages),
                   psi_ids=" ".join(sorted(named, key=lambda i: int(i.split("-")[1]))))
    return passages, docs


def ntrs_decision(rec: dict) -> tuple[bool, str]:
    c = rec.get("copyright") or {}
    kind = c.get("determinationType") or "not stated"
    basis = f"NTRS copyright determination: {kind}"
    if kind not in NTRS_PUBLIC:
        return False, basis + "; title and link only"
    if c.get("belongsToPublisher") or c.get("containsThirdPartyMaterial"):
        return False, basis + ", but marked as publisher-owned or containing third-party material; title and link only"
    return True, basis


def ntrs_passages(records: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    # which PSI investigations list each publication title
    listed: dict[str, dict] = {}
    for rec in records:
        for p in rec.get("publications") or []:
            t = clean(p.get("title") or "").strip()
            if t and norm(t):
                listed.setdefault(norm(t), {"title": t, "psi_ids": []})["psi_ids"].append(rec["accession"])
    files = {r["doc_id"]: r for r in manifest() if r["kind"] in ("ntrs_search", "ntrs_record")}
    matched: dict[int, dict] = {}  # ntrs id -> {rec, psi_ids, how}
    log = []
    for key, info in listed.items():
        doc_id = "search-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        row = files.get(doc_id)
        entry = {"publication_title": info["title"], "psi_ids": " ".join(dict.fromkeys(info["psi_ids"])), "status": "",
                 "ntrs_id": "", "ntrs_title": "", "title_similarity": "", "rights": "", "abstract_used": "no"}
        log.append(entry)
        if row is None or not row["saved_as"]:
            entry["status"] = "skipped: search not fetched" + (f" ({row['note']})" if row else "")
            continue
        results = json.loads((ROOT / row["saved_as"]).read_text(encoding="utf-8")).get("results") or []
        best, score = None, 0.0
        for r in results:
            s = 1.0 if norm(r.get("title") or "") == key else difflib.SequenceMatcher(None, key, norm(r.get("title") or "")).ratio()
            if s > score:
                best, score = r, s
        if best is None:
            entry["status"] = "skipped: NTRS returned no result"
            continue
        entry.update(ntrs_title=best.get("title") or "", title_similarity=f"{score:.2f}")
        if score < TITLE_MATCH:
            entry["status"] = f"skipped: no confident title match (best {score:.2f}, needs {TITLE_MATCH})"
            continue
        entry.update(status="matched", ntrs_id=str(best["id"]))
        m = matched.setdefault(int(best["id"]), {"rec": best, "psi_ids": [], "entries": []})
        m["psi_ids"] += info["psi_ids"]
        m["entries"].append(entry)
    # the FLEX technical publication, fetched by id
    row = files.get(f"ntrs-{FLEX_REPORT_ID}")
    if row and row["saved_as"]:
        rec = json.loads((ROOT / row["saved_as"]).read_text(encoding="utf-8"))
        matched.setdefault(FLEX_REPORT_ID, {"rec": rec, "psi_ids": [], "entries": []})["psi_ids"].append("PSI-69")

    passages, docs = [], []
    for ntrs_id in sorted(matched):
        m = matched[ntrs_id]
        rec, psi_ids = m["rec"], list(dict.fromkeys(m["psi_ids"]))
        use, basis = ntrs_decision(rec)
        abstract = [p for p in paragraphs(rec.get("abstract") or "") if len(p) >= MIN_CHARS]
        doc_id, title, url = f"ntrs-{ntrs_id}", clean(rec.get("title") or "").strip(), NTRS_PAGE.format(ntrs_id)
        note = ""
        if use and not abstract:
            use, note = False, "no abstract text in the NTRS record"
        if use:
            for n, text in enumerate(abstract, 1):
                passages.append(passage(f"{doc_id}-{n}", text, "ntrs_abstract", doc_id, title, "abstract", url, psi_ids))
        for e in m["entries"]:
            e.update(rights=basis, abstract_used="yes" if use else "no")
        docs.append({"doc_id": doc_id, "source_type": "ntrs_abstract", "title": title, "url": url, "rights_basis": basis,
                     "text_used": "yes" if use else "no", "passages": len(abstract) if use else 0,
                     "psi_ids": " ".join(psi_ids), "note": note})
    return passages, docs, log


def _rng(s: pd.Series, digits: int = 2) -> str:
    s = s.dropna()
    return "not stated" if s.empty else f"{round(float(s.min()), digits):g} to {round(float(s.max()), digits):g}"


def card_passages() -> tuple[list[dict], list[dict]]:
    """Passages computed from NASA tables. Every number is computed here from the file named in the text."""
    passages, docs = [], []
    cat = pd.read_csv(CATALOG, dtype=str, keep_default_na=False)
    uni = pd.read_csv(UNIFIED, dtype=str, keep_default_na=False)
    num = lambda g, c: pd.to_numeric(g[c].where(g[c] != ""))  # noqa: E731
    say = lambda v: v if v else "not stated"                 # noqa: E731
    for _, r in cat.iterrows():
        pid, name = r["psi_id"], r["acronym"] or r["name"]
        text = (f"{pid} {name} ({r['name']}), computed from data/catalog/investigations.csv: fire-safety pillar "
                f"{say(r['fire_safety_pillar'])}; fuel phase {say(r['fuel_phase'])}; hardware {say(r['hardware'])}; "
                f"ambient O2 range {say(r['o2_min_frac'])} to {say(r['o2_max_frac'])} (mole fraction); "
                f"oxidizer-stream O2 range {say(r['o2_stream_min_frac'])} to {say(r['o2_stream_max_frac'])} (mole fraction); "
                f"pressure range {say(r['pressure_min_kpa'])} to {say(r['pressure_max_kpa'])} kPa.")
        g = uni[uni["psi_id"] == pid]
        if len(g):
            fuels = [f for f in dict.fromkeys(g["fuel"]) if f]
            text += (f" Computed from data/unified/tests_conditions.csv: {len(g)} rows from {g['source_file'].nunique()} "
                     f"experimental table(s); O2 filled in {int(num(g, 'o2_mole_frac').notna().sum())} rows, pressure in "
                     f"{int(num(g, 'pressure_kpa').notna().sum())}, flow speed in "
                     f"{int(num(g, 'flow_speed_cm_s').notna().sum())}, sample size in "
                     f"{int(num(g, 'sample_size_mm').notna().sum())}; {len(fuels)} distinct fuel entries"
                     + (f" (first: {', '.join(fuels[:4])})" if fuels else "") + ".")
        else:
            text += " data/unified/tests_conditions.csv has no rows for this investigation (PSI offers no experimental table)."
        doc_id = f"card-{pid}"
        passages.append(passage(f"{doc_id}-1", text, "data_card", doc_id, f"Data card: {pid} {name}", "catalog and unified table",
                                r["source_url"], [pid], acronym=r["acronym"], investigation=r["name"]))
        docs.append({"doc_id": doc_id, "source_type": "data_card", "title": f"Data card: {pid} {name}", "url": r["source_url"],
                     "rights_basis": "computed by this project from NASA tables (CC0 where PSI states it)",
                     "text_used": "yes", "passages": 1, "psi_ids": pid, "note": ""})

    f = pd.read_csv(FLEX_CLEAN)
    src = "computed from data/clean/flex_clean.csv (NASA PSI-69 experimental table)"
    count = lambda s: ", ".join(f"{k} {v}" for k, v in s.value_counts().items())  # noqa: E731
    cards = [
        ("fuel and test end",
         f"FLEX (PSI-69) test counts, {src}: {len(f)} tests on {f['test_date'].nunique()} test dates from "
         f"{f['test_date'].min()} to {f['test_date'].max()}. By fuel: {count(f['fuel'])}. By test end: {count(f['test_end'])}. "
         f"Initial droplet diameter {_rng(f['d0_mm'])} mm ({int(f['d0_mm'].isna().sum())} tests have none)."),
        ("diluent",
         f"FLEX (PSI-69) diluents, {src}: {int((f['diluent'] == 'CO2').sum())} tests used CO2 as the diluent "
         f"(mole fraction {_rng(f.loc[f['diluent'] == 'CO2', 'co2_mole_frac'])}), {int((f['diluent'] == 'He').sum())} tests "
         f"used helium (He) as the diluent (mole fraction {_rng(f.loc[f['diluent'] == 'He', 'he_mole_frac'])}), and "
         f"{int((f['diluent'] == 'none').sum())} tests had neither (O2 and N2 only). "
         f"{int(((f['co2_mole_frac'] > 0) & (f['he_mole_frac'] > 0)).sum())} tests mixed CO2 and He."),
        ("pressure and oxygen",
         f"FLEX (PSI-69) atmospheres, {src}: ambient pressure {_rng(f['pressure_mmhg'].where(f['pressure_mmhg'] > 0), 0)} mmHg "
         f"({_rng(f['pressure_atm'])} atm); {int((f['pressure_band'] == 'near_760').sum())} tests near 760 mmHg, "
         f"{int((f['pressure_band'] == 'near_535').sum())} near 535 mmHg and {int((f['pressure_band'] == 'above_900').sum())} "
         f"above 900 mmHg; {int(f['pressure_band'].isna().sum())} test has its pressure printed as 0 and is left without a "
         f"pressure. Ambient O2 mole fraction {_rng(f['o2_mole_frac'])}."),
        ("measurements",
         f"FLEX (PSI-69) measurements, {src}: burning rate K {_rng(f['burning_rate_k'])} (unit unconfirmed; "
         f"{int(f['burning_rate_k'].notna().sum())} tests have a value); extinction ratio d_ext/d0 "
         f"{_rng(f['d_ext_over_d0'])} ({int(f['d_ext_over_d0'].notna().sum())} tests have a value); "
         f"{int((~f['quality_flag'].fillna('none').isin(['none', ''])).sum())} tests carry a quality flag."),
    ]
    url = "https://doi.org/10.60555/mbq8-0451"
    for n, (section, text) in enumerate(cards, 1):
        passages.append(passage(f"card-flex-{n}", text, "data_card", "card-flex", "Data card: FLEX test table", section, url,
                                ["PSI-69"], acronym="FLEX", investigation="Flame Extinguishment Experiment"))
    docs.append({"doc_id": "card-flex", "source_type": "data_card", "title": "Data card: FLEX test table", "url": url,
                 "rights_basis": "computed by this project from the NASA PSI-69 table (CC0)", "text_used": "yes",
                 "passages": len(cards), "psi_ids": "PSI-69", "note": ""})
    return passages, docs


def build() -> tuple[list[dict], dict, list[dict], list[dict]]:
    """(passages, PSI field summary, documents, NTRS log)"""
    records = load_records()
    pats = name_patterns(records)
    psi, psi_docs, found = psi_passages(records)
    seen = {p["text"] for p in psi}
    pages, page_docs = page_passages(pats, seen)
    report, report_docs = report_passages(pats, seen)
    ntrs, ntrs_docs, log = ntrs_passages(records)
    cards, card_docs = card_passages()
    return psi + pages + report + ntrs + cards, found, psi_docs + page_docs + report_docs + ntrs_docs + card_docs, log


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    passages, found, docs, log = build()
    ids = [p["passage_id"] for p in passages]
    assert len(ids) == len(set(ids)), "passage ids must be unique"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for p in passages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    write_csv(DOCUMENTS, docs)
    if log:
        write_csv(NTRS_LOG, log)
    print(f"{len(passages)} passages -> {OUT.relative_to(ROOT)}")
    by_type = pd.DataFrame(passages).groupby("source_type").agg(passages=("passage_id", "size"), documents=("doc_id", "nunique"))
    print(by_type.to_string())
    d = pd.DataFrame(docs)
    print("\nDocuments by type and text use:\n", d.groupby(["source_type", "text_used"]).size().to_string())
    if log:
        lg = pd.DataFrame(log)
        print("\nNTRS lookups:", len(lg))
        print(lg["status"].str.replace(r"\(best.*", "", regex=True).value_counts().to_string())
        print("rights of matched:\n", lg.loc[lg["status"] == "matched", "rights"].value_counts().to_string())


if __name__ == "__main__":
    main()
