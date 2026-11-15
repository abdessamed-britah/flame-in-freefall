# Ask NASA's records: retrieval and support check (2026-11-15)

Reproduce with `python src/eval_retrieval.py` and `python src/support_calibration.py`.

## Corpus

874 passages in `data/corpus/passages.jsonl`; documents and rights in `data/corpus/documents.csv`;
NTRS lookups in `data/corpus/ntrs_log.csv`.

| Source type | Documents with text | Passages |
|---|---|---|
| psi_record (24 PSI records) | 24 | 558 |
| nasa_page (6 challenge resource pages) | 6 | 83 |
| nasa_report (Researcher's Guide to Combustion Science, PDF) | 1 | 175 |
| ntrs_abstract (NASA NTRS) | 26 | 30 |
| data_card (computed from NASA tables) | 25 | 28 |

NTRS: 292 distinct publication titles from the PSI records were searched, one request each.

| Outcome | Titles |
|---|---|
| NTRS returned no result (mostly journal papers that NTRS does not hold) | 192 |
| No confident title match (similarity below 0.92) | 37 |
| Matched | 62 |
| Search not fetched | 1 |

The 62 matched titles are 60 distinct NTRS records; with NASA/TP-2015-216046 (fetched by id) that
is 61 NTRS documents. Abstract text is used for 26 of them: those whose NTRS copyright
determination is PUBLIC_USE_PERMITTED or GOV_PUBLIC_USE_PERMITTED and that are not marked as
publisher-owned or containing third-party material. The other 35 (determination "not stated" for
31, "OTHER" for 4) are kept as title and link only. The one search not fetched is the Researcher's
Guide itself, which is in the corpus from its PDF.

## Retrieval: hit rate at top 6

30 questions in `tests/retrieval_questions.json`, written before any retrieval was run on the new
corpus. A hit: one of the 6 retrieved passages belongs to an expected document or is linked to an
expected investigation. Ranker: TF-IDF (word 1-2 grams), with a quota per kind of source.

| Group | Questions | Hits |
|---|---|---|
| original (the 10 earlier questions) | 10 | 10 |
| findings (need the new documents) | 10 | 10 |
| reworded (few words shared with the source text) | 10 | 8 |
| all | 30 | 28 |

Misses, both reworded: "Which inert gases were added to put out burning fuel spheres?" (FLEX) and
"Burning of two-liquid mixtures as small spheres" (FLEX-2). TF-IDF cannot link "spheres" to
"droplets" or "two-liquid" to "bi-component".

**Embeddings were not added.** The rule set beforehand was to add them only if the reworded group
scored below 7 of 10; it scored 8.

Quota per kind among the 6: PSI record paragraphs 3, PSI publication titles 1, NASA web pages 3,
NASA report 2, NTRS abstracts 2, data cards 1. One adjustment was made after a preliminary run on a
partly fetched corpus (publication titles 2 to 1, web pages 2 to 3), because short titles were
taking places from paragraphs; on that partial corpus the change moved the reworded group from 8 to
7, so it was not made to raise the score. The questions were not changed.

## Support check

For each bullet of an answer: the share of its content words (lower-cased, stop words and plural s
removed) found in the passages it cites. A bullet below the threshold is shown with a "weakly
supported" flag; it is not hidden.

Threshold: **0.50**. On the 7 saved answers (12 bullets, all of which passed the citation check):

| Bullets scored against | n | min | median | max | below 0.50 |
|---|---|---|---|---|---|
| the passages they cite | 12 | 0.83 | 1.00 | 1.00 | 0 |
| retrieved passages they do not cite (a wrong citation) | 53 | 0.00 | 0.20 | 0.57 | 49 |

0.50 sits in the gap between the two groups: no correctly cited bullet is flagged, and 49 of 53
wrong citations would be. It is a word count, not a judgement of meaning: a bullet can reuse the
words of a passage and still misstate it, and a faithful paraphrase in different words can be
flagged. The sample is small (12 bullets from one model).
