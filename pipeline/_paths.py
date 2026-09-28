"""Shared paths for the pipeline. Override with environment variables:
  HKMAP_WORK  working folder for downloads, extracted text and heavy intermediates (default: <repo>/work)
  HKMAP_SITE  folder holding index.html, app.js, data.js, layout.js (default: the repo root)
Small intermediate JSON (inventory, graph/) is written next to these scripts."""
import os
from pathlib import Path

PIPE = Path(__file__).resolve().parent
REPO = PIPE.parent
WORK = Path(os.environ.get("HKMAP_WORK", REPO / "work"))
SITE = Path(os.environ.get("HKMAP_SITE", REPO))
