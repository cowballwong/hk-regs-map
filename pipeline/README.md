# Pipeline

These Python scripts built `data.js` and `layout.js` for the map. They are published so the method can be read and reused. They are research scripts, not a packaged tool, and they were run step by step with manual review between the steps.

**Not included:** the downloaded PDFs, extracted text, OCR output, the corpus, and the intermediate graph and tag files. The source documents belong to their publishers and are not redistributed; run the download steps yourself to rebuild them.

## Setup

- Python 3.11 or later.
- Packages: `requests`, `beautifulsoup4`, `lxml`, `pymupdf` (imported as `fitz`), `playwright` (then `playwright install chromium`); optional `striprtf` and `openpyxl` for the few RTF and XLSX documents.
- Paths, all set in `_paths.py`:
  - `HKMAP_WORK` is the working folder for downloads, text and heavy intermediates (default `../work`, which is git-ignored);
  - `HKMAP_SITE` is the folder holding `index.html` and the site scripts (default: the repository root);
  - small intermediate JSON (the inventory and `graph/`) is written next to the scripts and is git-ignored.
- OCR only: set `GOOGLE_AI_API_KEY` in your environment to a Google AI Studio key. No key is stored in this repository.

Be polite to the government sites. The fetchers wait at least 2.5 seconds between requests to each host, cache pages, and resume instead of re-downloading. Read each site's terms of use first.

## Steps

| Step | Script | What it does |
|---|---|---|
| S2 | `s2_parse_legislation.py` | Parses the Hong Kong e-Legislation XML for Cap. 123 and its subsidiary legislation (English and Traditional Chinese) into one record per section, regulation or schedule. First put the XML from the [e-Legislation bulk download](https://data.gov.hk/) in `<work>/raw/legislation/`. |
| S3 | `fetch.py` | A polite, cached page fetcher used by the S3 scripts. |
| S3 | `s3_bd.py`, `s3_landsd.py`, `s3_pland.py`, `s3_fsd.py` | Build a document inventory from each department's own index pages (English and Chinese): codes, titles, dates, status and URLs. Index pages only; no PDFs. |
| S3 | `s3_merge.py` | Merges the four inventories into `S3_inventory.json`. |
| S4 | `s4_download.py` | Downloads every document in the inventory (PNAPs from BD's official bundle zips) and writes a manifest. |
| S4 | `s4_extract.py` | Extracts page-split text and writes `corpus.jsonl`, flagging scanned documents for OCR. |
| S4 | `s4_ocr.py` | OCR of scanned pages with Gemini 2.5 Flash, faithful transcription only, with a hard cost cap. |
| S5 | `s5_graph.py` | Builds the nodes (documents, the legislation tree, external ordinances) and the solid citation layer by pattern matching. Each edge keeps the quoted sentence and page. Deterministic, no AI. |
| S5 | `s5_taxonomy_batches.py` | Writes the domain and subject taxonomy (in BD's own vocabulary) and splits the documents into tagging batches. |
| S5 | `s5_final.py concepts \| graph \| candidates \| bridges` | Builds concepts and `graph.json`, prepares the dashed bridge candidates with text snippets, and merges the verified bridges. |
| S6 | `s6_build_data.py` | Turns the graph into the compact `data.js` (`window.HKMAP`). |
| S6 | `s6_bake_layout.py` | Runs the site's own force layout in headless Chromium and saves the settled positions to `layout.js`. |
| S7 | `s7_download.py`, `s7_extract.py`, `s7_ocr.py` | Gap filling: resumable downloads of documents missed in S4, text extraction for them, and targeted OCR of garbled pages. |
| S7 | `s7_merge.py` | Merges `graph.json`, the checked tags and a hand-maintained `graph/fixes.json` into `graph_final.json`. |
| S7 | `s7_artifact.py` | Optional: writes a copy of the site without the doctype, html, head and body wrapper (for hosts that supply their own) and runs page checks. |

Typical rebuild after the data changes:

```
python s7_merge.py
python s6_build_data.py
python s6_bake_layout.py
```

## The AI steps

Two steps were done by AI outside these scripts, and their outputs are not in the repository:

- **Tagging and summaries.** For each batch from `s5_taxonomy_batches.py`, an AI model read the full text of each document and wrote the domain, subjects and the English and Chinese summaries (`graph/tags/batch_*_tags_v2.json`). A second pass checked each summary against the text.
- **Bridge verification.** For the candidates from `s5_final.py candidates`, an AI model read both texts and kept only the pairs with a real, stated connection, each with a written reason (`<work>/graph_work/bridges_verified_*.json`). `s5_final.py bridges` merges them.

The solid citation layer uses no AI.
