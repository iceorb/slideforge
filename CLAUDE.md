# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fruzaqla Presentation Pipeline — a Python system that generates HTML presentation slides for the pharmaceutical brand "Fruzaqla" using AI-driven planning and compliance-approved content extracted from uploaded PDFs. The key constraint: the LLM selects from pre-approved content only; it never generates clinical text.

Uses **Claude (Anthropic API)** for LLM calls. Two models configured in `config.py`:
- `LLM_MODEL` (`claude-opus-4-6`) — planning, content selection, CSS generation, slide HTML generation
- `LLM_MODEL_LIGHT` (`claude-haiku-4-5-20251001`) — PDF file classification

Uses **sentence-transformers** (`all-MiniLM-L6-v2`) for local embedding-based retrieval. No external vector DB or embedding API.

## Commands

```bash
# Install dependencies (includes sentence-transformers, torch, numpy)
pip3 install -r fruzaqla_pipeline/requirements.txt

# Run Streamlit App (recommended)
python3 -m streamlit run fruzaqla_pipeline/app.py

# Run CLI (slide count is determined from the prompt text, not a flag)
python3 fruzaqla_pipeline/main.py --query "Make a 3 slide presentation on Fruzaqla efficacy and safety"
python3 fruzaqla_pipeline/main.py --query "Test query" --mock
```

There are no automated tests, linting, or build steps configured.

## Architecture

The system is a 4-stage pipeline: **Ingestion → Planning → Retrieval → Generation**.

All core code lives in `fruzaqla_pipeline/`:

- **`config.py`** — API keys, model names (`LLM_MODEL`, `LLM_MODEL_LIGHT`), directory paths.
- **`ingestor.py`** — PDF processing and indexing. Classifies PDFs by filename keywords, falls back to Haiku LLM reading the first page. Routes:
  - Style guide PDFs → sent directly to Claude via **document API** (`_encode_pdf`) → Opus generates `style.css` (brand CSS with slide context). The full PDF is uploaded so Claude can see color swatches, font specimens, spacing examples, and brand motifs.
  - Visual aid PDFs → image extraction + tagging → `image_index.json`. The visual aid PDF is also sent directly to template generation (see below).
  - After CSS + visual aid processing: Opus generates `slide_template.html` — the **visual aid PDF** is sent directly via document API alongside the CSS so the LLM can replicate the real branded layout (two-column ISI sidebar, nav bar, logo placement, data table structure, etc.). Produces multiple layout variations (title, two-column-with-isi, data-table, flowchart, stats-highlight).
  - Prescribing info PDFs → text extraction → `local_content.txt` → builds `embedding_index.json` (semantic vector index via sentence-transformers)
- **`planner.py`** — `Planner` class. Calls Claude to generate a JSON slide outline (slide count is agentic — determined by the LLM from the prompt). Also calls Claude to select the best approved content items for each slide. Helper functions `extract_json()` and `extract_text_from_response()` handle markdown code fences and thinking blocks in Claude responses.
- **`retrieval.py`** — `Retrieval` class. Embedding-based semantic search over chunked PI content (`embedding_index.json`) and image descriptions. Uses cosine similarity with `all-MiniLM-L6-v2`. The embedding model is lazy-loaded. `build_index()` is called during ingestion to chunk text and create embeddings. `chunk_text()` splits with overlap respecting sentence boundaries.
- **`generator.py`** — `Generator` class. Loads `slide_template.html` (the reference brand template) and passes it to the LLM as a design guide. The LLM generates structured HTML for each slide that follows the template's layout patterns (grids, cards, stat-blocks, tables, callouts). The outer HTML shell comes from `templates/slide.html` (Jinja2) with the brand CSS injected.
- **`main.py`** — CLI entry point.
- **`app.py`** — Streamlit web UI. Two generate buttons: "Generate Presentation" (uses existing ingested data) and "Reprocess Inputs & Generate" (re-ingests PDFs with slide context before generating).

### Data flow

1. **Ingestion** (via "Reprocess Inputs & Generate" or sidebar button): PDFs → `inputs/local_content.txt`, `inputs/embedding_index.json`, `inputs/image_index.json`, `inputs/style.css`, `inputs/slide_template.html`
2. **Planning**: User query → `Planner.generate_outline()` → JSON outline (LLM decides slide count)
3. **Retrieval**: Each slide description → `Retrieval.search_claims()` → cosine similarity over embedding index + image descriptions
4. **Selection**: `Planner.select_content_for_slide()` → LLM picks best items from retrieved set
5. **Generation**: `Generator.generate_slide_html()` → LLM creates structured HTML following `slide_template.html` → rendered into `templates/slide.html` with brand CSS → HTML files in `output/`

### Key design decisions

- **Local embedding retrieval** — `all-MiniLM-L6-v2` via sentence-transformers. Chunks PI text with overlap, embeds at ingestion, cosine similarity at query time. No external vector DB.
- **PDF-direct design system** — Style guide PDF is sent directly to Claude via document API → `style.css`. Visual aid PDF + CSS → `slide_template.html` (also via document API). The full PDFs are uploaded so Claude can see every page — color swatches, font specimens, real slide layouts. Different visual aids produce different templates.
- **Agentic slide count** — The LLM determines the number of slides from the user's natural language prompt (no slider/flag).
- **Two-button UI** — "Generate Presentation" skips re-ingestion (fast, for same files). "Reprocess Inputs & Generate" re-ingests with slide context (for new/changed files).
- **Mock mode** — `mock=True` flag on all classes for testing without API calls. Defaults to off in Streamlit.

## Inputs and Outputs

- `inputs/` — Upload PDFs here (via Streamlit or manually). After ingestion contains:
  - `style.css` — Brand CSS generated from style guide
  - `slide_template.html` — Reference HTML layouts generated from CSS + visual aid PDF (via document API)
  - `embedding_index.json` — Semantic vector index of PI content
  - `image_index.json` — Tagged image metadata
  - `local_content.txt` — Raw extracted PI text
  - `images/` — Extracted image files
- `output/` — Generated HTML slide files (`slide_1.html`, `slide_2.html`, etc.)
