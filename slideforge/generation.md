# Generation Pipeline

This document details how the generation pipeline creates HTML slides from ingested content.

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              GENERATION PIPELINE                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘

   USER QUERY                                                           OUTPUT SLIDES
       │                                                                      ▲
       ▼                                                                      │
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│   PLANNER    │───▶│  RETRIEVAL   │───▶│   PLANNER    │───▶│    GENERATOR        │
│              │    │              │    │  (select)    │    │                      │
│ Generate     │    │ Search for   │    │ Choose best  │    │ Build HTML slides   │
│ outline      │    │ content      │    │ content      │    │ with brand styling  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────────────┘
       │                   ▲                   │                       │
       │                   │                   │                       │
       ▼                   │                   ▼                       ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│ JSON outline │    │ embedding_   │    │ Selected     │    │ output/slides_*/     │
│ with slide   │    │ index.json   │    │ content      │    │ slide_1.html         │
│ titles       │    │ image_index  │    │ items        │    │ slide_2.html ...     │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────────────┘
```

---

## Detailed Flow

### Phase 1: Planning

```
  ┌────────────────────────────────────────────────────────────────────────────────────┐
  │                         Planner.generate_outline()                                  │
  └────────────────────────────────────────────────────────────────────────────────────┘
                                           │
       user_query ────────────────────────▶│
       "Create a 5-slide deck on          │
        Fruzaqla efficacy"                 │
                                           ▼
                            ┌──────────────────────────────────┐
                            │         CLAUDE LLM               │
                            │                                  │
                            │  - Determine # of slides         │
                            │  - Create titles & descriptions  │
                            │  - thinking: {type: "adaptive"}  │
                            └──────────────┬───────────────────┘
                                           │
                                           ▼
                            ┌──────────────────────────────────┐
                            │  JSON Output:                    │
                            │  {                               │
                            │    "slides": [                   │
                            │      {"title": "Efficacy",       │
                            │       "topic_description": ...}  │
                            │    ]                             │
                            │  }                               │
                            └──────────────────────────────────┘
```

### Phase 2: Retrieval

```
  ┌────────────────────────────────────────────────────────────────────────────────────┐
  │                        Retrieval.search_claims()                                    │
  │                                                                                     │
  │  Combined search: PI content + visual aids                                          │
  └────────────────────────────────────────────────────────────────────────────────────┘
                                           │
       slide.topic_description ───────────▶│
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 ▼                                                   ▼
  ┌──────────────────────────────┐                   ┌──────────────────────────────┐
  │   search_content()           │                   │   search_images()            │
  │                              │                   │                              │
  │   Load embedding_index.json  │                   │   Load image_index.json      │
  │   Cosine similarity search   │                   │   Cosine similarity search   │
  │   Return top_k (default 5)   │                   │   Return top_k (default 3)   │
  └──────────────────────────────┘                   └──────────────────────────────┘
                 │                                                   │
                 └─────────────────────┬─────────────────────────────┘
                                       │
                                       ▼
                 ┌─────────────────────────────────────────────────────┐
                 │   MERGE RESULTS                                     │
                 │   Sort by score descending                          │
                 │   Return top (k + 3) items                          │
                 └─────────────────────────────────────────────────────┘
```

### Phase 3: Content Selection

```
  ┌────────────────────────────────────────────────────────────────────────────────────┐
  │                  Planner.select_content_for_slide()                                 │
  └────────────────────────────────────────────────────────────────────────────────────┘
                                        │
       slide_topic ─────────────────────┤
       retrieved_items ─────────────────┤
                                        ▼
                         ┌──────────────────────────────────┐
                         │         CLAUDE LLM               │
                         │                                  │
                         │  "Select BEST pieces of          │
                         │   approved content.              │
                         │   Do NOT invent new text."       │
                         └──────────────┬───────────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────────┐
                         │  {                               │
                         │    "selected_item_ids": [...],   │
                         │    "layout_suggestion": "..."    │
                         │  }                               │
                         └──────────────────────────────────┘
```

### Phase 4: Slide Generation

```
  ┌────────────────────────────────────────────────────────────────────────────────────┐
  │                    Generator.generate_slide_html()                                  │
  └────────────────────────────────────────────────────────────────────────────────────┘
                                        │
       slide_title ─────────────────────┤
       selected_content ────────────────┤
                                        │
                  ┌─────────────────────┴─────────────────────┐
                  ▼                                           ▼
   ┌────────────────────────────┐            ┌────────────────────────────┐
   │   _load_css()              │            │   _load_slide_template()   │
   │   Read inputs/style.css    │            │   Read slide_template.html │
   └────────────┬───────────────┘            └────────────┬───────────────┘
                │                                         │
                └─────────────────────┬───────────────────┘
                                      ▼
   ┌───────────────────────────────────────────────────────────────────────────────────┐
   │                           CLAUDE LLM                                               │
   │                                                                                    │
   │   "Create NEW slide with APPROVED CONTENT as main text                             │
   │    Use template's HTML structure, class names, CSS patterns                        │
   │    Keep nav bar, ISI sidebar, footer from template"                                │
   └───────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌───────────────────────────────────────────────────────────────────────────────────┐
   │   JINJA2 TEMPLATE RENDERING                                                        │
   │   template.render(title, body_content, css_styles)                                 │
   └───────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌───────────────────────────────────────────────────────────────────────────────────┐
   │   SAVE: output/slides_YYYYMMDD_HHMM/slide_N.html                                   │
   └───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Content Deduplication

```
  used_content_ids = set()   ← initialized before processing slides

  For each slide:
    1. RETRIEVE: Get candidate content items
    2. FILTER: Remove items already in used_content_ids
    3. SELECT: LLM chooses best from filtered list
    4. TRACK: Add selected IDs to used_content_ids

  Result: Each piece of content appears on at most one slide
```

---

## Output Structure

```
output/
├── images/                            ← Shared extracted assets
│
└── slides_20260206_1430/              ← Timestamped output folder
    ├── images/                        ← Copy for portability
    ├── slide_1.html
    ├── slide_2.html
    └── slide_N.html
```
