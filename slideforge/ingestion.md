# Ingestion Pipeline

This document details how the ingestion pipeline processes source PDFs and prepares content for slide generation.

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              INGESTION PIPELINE                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐     ┌──────────────────┐     ┌────────────────────────────────────────┐
  │   INPUT/     │     │    CLASSIFY      │     │           ROUTE BY TYPE                │
  │   PDFs       │────▶│    PDF TYPE      │────▶│                                        │
  └──────────────┘     └──────────────────┘     │  ┌──────────┬──────────┬──────────┐   │
                        filename keywords        │  │ style_   │ visual_  │prescribing│   │
                        or LLM fallback          │  │ guide    │ aid      │ _info     │   │
                                                 │  └────┬─────┴────┬─────┴────┬──────┘   │
                                                 └───────┼──────────┼──────────┼──────────┘
                                                         │          │          │
         ┌───────────────────────────────────────────────┘          │          │
         ▼                                                          │          │
  ┌────────────────┐                                                │          │
  │  GENERATE CSS  │                                                │          │
  │  (Claude LLM)  │                                                │          │
  │                │                                                │          │
  │ Send full PDF  │                                                │          │
  │ to extract:    │                                                │          │
  │ - Colors       │                                                │          │
  │ - Fonts        │                                                │          │
  │ - Spacing      │                                                │          │
  │ - Brand rules  │                                                │          │
  └───────┬────────┘                                                │          │
          │                                                         │          │
          ▼                                                         │          │
  ┌────────────────┐                               ┌────────────────┘          │
  │  style.css     │                               ▼                           │
  │  (saved to     │                   ┌──────────────────────┐                │
  │   inputs/)     │                   │ EXTRACT IMAGES VIA   │                │
  └───────┬────────┘                   │ UNSTRUCTURED API     │                │
          │                            │                      │                │
          │                            │ - hi_res strategy    │                │
          │                            │ - Extract Image/Table│                │
          │                            │ - Get element coords │                │
          │                            └──────────┬───────────┘                │
          │                                       ▼                            │
          │                            ┌──────────────────────┐                │
          │                            │ CREATE EMBEDDINGS    │                │
          │                            │ (SentenceTransformer)│                │
          │                            │                      │                │
          │                            │ Model: all-MiniLM-   │                │
          │                            │        L6-v2         │                │
          │                            └──────────┬───────────┘                │
          │                                       ▼                            │
          │                            ┌──────────────────────┐    ┌───────────┘
          │                            │  image_index.json    │    ▼
          │                            │  (saved to inputs/)  │  ┌────────────────────┐
          │                            │                      │  │ EXTRACT TEXT       │
          │                            │  Contains:           │  │ (pypdf)            │
          │                            │  - path              │  │                    │
          │                            │  - type              │  │ Read all pages,    │
          │                            │  - label             │  │ concatenate text   │
          │                            │  - description       │  └─────────┬──────────┘
          │                            │  - embedding[]       │            │
          │                            └──────────┬───────────┘            ▼
          │                                       │            ┌────────────────────┐
          │                                       │            │ CHUNK TEXT         │
          │                                       │            │ (retrieval.py)     │
          │                                       │            │                    │
          │                                       │            │ - 500 char chunks  │
          │                                       │            │ - 100 char overlap │
          │                                       │            │ - Sentence aware   │
          │                                       │            └─────────┬──────────┘
          │                                       │                      │
          │                                       │                      ▼
          │                                       │            ┌────────────────────┐
          │                                       │            │ BUILD EMBEDDINGS   │
          │                                       │            │ (SentenceTransformer)
          │                                       │            │                    │
          │                                       │            │ Encode each chunk  │
          │                                       │            └─────────┬──────────┘
          │                                       │                      │
          │                                       │                      ▼
          │                                       │            ┌────────────────────┐
          ▼                                       │            │ embedding_index.json
  ┌────────────────┐                              │            │ local_content.txt  │
  │ GENERATE SLIDE │                              │            │ (saved to inputs/) │
  │ TEMPLATE       │◀─────────────────────────────┘            └────────────────────┘
  │ (Claude LLM)   │
  │                │
  │ Sends both PDFs│
  │ (visual_aid +  │
  │  style_guide)  │
  │                │
  │ + key assets   │
  │ from image_    │
  │ index.json     │
  │                │
  │ Generates:     │
  │ - Full HTML5   │
  │ - Brand styling│
  │ - Logo refs    │
  └───────┬────────┘
          │
          ▼
  ┌────────────────┐
  │ templates/     │
  │ slide.html     │
  └────────────────┘
```

---

## PDF Classification Flow

```
                         ┌─────────────────────────────────────┐
                         │           classify_pdf()            │
                         └─────────────────────────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────────┐
                         │  Check filename against keywords:   │
                         │                                     │
                         │  style_guide → "style", "brand"     │
                         │  visual_aid  → "visual", "aid"      │
                         │  prescribing → "prescribing", "pi"  │
                         └──────────────────┬──────────────────┘
                                            │
                             ┌──────────────┴──────────────┐
                             │                             │
                        [MATCH]                       [NO MATCH]
                             │                             │
                             ▼                             ▼
                   ┌─────────────────┐         ┌─────────────────────┐
                   │ Return doc_type │         │ LLM FALLBACK        │
                   └─────────────────┘         │ Extract first page  │
                                               │ Send to Claude      │
                                               └─────────────────────┘
```

---

## Output Files Summary

```
inputs/
├── style.css            ← Generated CSS from style guide
├── image_index.json     ← Tagged images with embeddings
├── local_content.txt    ← Raw text from prescribing info
└── embedding_index.json ← Chunked PI text with embeddings

output/
└── images/              ← Extracted image files

templates/
└── slide.html           ← Reference HTML template
```
