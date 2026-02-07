# FRUZAQLA Pipeline - System Architecture

## High-Level Flow

```mermaid
flowchart TB
    subgraph Input["📁 Input PDFs"]
        SG[Style Guide PDF]
        VA[Visual Aid PDF]
        PI[Prescribing Info PDF]
    end

    subgraph Ingestion["🔧 Ingestion (ingestor.py)"]
        CLASSIFY[PDF Classification]
        CSS[CSS Generation<br/>Claude Vision]
        TEMPLATE[Template Generation<br/>Claude Vision + Assets]
        EXTRACT[Asset Extraction<br/>Unstructured API]
        EMBED[Embedding Creation<br/>sentence-transformers]
    end

    subgraph Storage["💾 Storage"]
        INPUTS[("inputs/")]
        IMAGES[("output/images/")]
        STYLE[style.css]
        TMPL[slide_template.html]
        EMBIDX[embedding_index.json]
        IMGIDX[image_index.json]
    end

    subgraph Generation["⚡ Generation"]
        PLAN[Outline Planning<br/>planner.py]
        RETRIEVE[Content Retrieval<br/>retrieval.py]
        GEN[Slide Generation<br/>generator.py]
    end

    subgraph Output["📤 Output"]
        SLIDES[("output/slides_*/")]
        HTML[slide_1.html<br/>slide_2.html<br/>...]
        ASSETS[images/]
    end

    SG --> CLASSIFY
    VA --> CLASSIFY
    PI --> CLASSIFY

    CLASSIFY --> CSS
    CLASSIFY --> EXTRACT
    CLASSIFY --> EMBED

    CSS --> STYLE
    EXTRACT --> IMAGES
    EXTRACT --> IMGIDX
    EMBED --> EMBIDX

    IMGIDX --> TEMPLATE
    STYLE --> TEMPLATE
    VA --> TEMPLATE
    TEMPLATE --> TMPL

    EMBIDX --> RETRIEVE
    IMGIDX --> RETRIEVE
    TMPL --> GEN

    PLAN --> GEN
    RETRIEVE --> GEN

    GEN --> HTML
    IMAGES --> ASSETS
    HTML --> SLIDES
    ASSETS --> SLIDES
```

## Component Details

```mermaid
flowchart LR
    subgraph ingestor["ingestor.py"]
        A1[classify_pdf]
        A2[extract_text]
        A3[extract_images_unstructured]
        A4[generate_css]
        A5[generate_slide_template]
    end

    subgraph retrieval["retrieval.py"]
        B1[search_content]
        B2[search_images]
        B3[search_claims]
    end

    subgraph planner["planner.py"]
        C1[generate_outline]
        C2[select_content_for_slide]
    end

    subgraph generator["generator.py"]
        D1[_generate_slide_body]
        D2[generate_slide_html]
    end
```

## Data Flow

```
User Prompt
    │
    ▼
┌─────────────────┐
│  planner.py     │ ──► Outline (slides array)
└─────────────────┘
    │
    │  For each slide:
    ▼
┌─────────────────┐
│  retrieval.py   │ ──► PI excerpts + matching images
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  planner.py     │ ──► Selected content for slide
└─────────────────┘
    │
    ▼
┌─────────────────┐     ┌──────────────────────┐
│  generator.py   │ ◄── │ slide_template.html  │
└─────────────────┘     │ previous_slide.html  │
    │                   │ available images     │
    ▼                   └──────────────────────┘
output/slides_YYYYMMDD_HHMM/slide_N.html
```

## File Structure

```
solstice-onsite/
├── fruzaqla_pipeline/
│   ├── app.py              # Streamlit UI
│   ├── config.py           # API keys
│   ├── ingestor.py         # PDF processing
│   ├── retrieval.py        # Semantic search
│   ├── planner.py          # Outline & selection
│   ├── generator.py        # HTML generation
│   └── templates/
│       └── slide.html      # Jinja2 wrapper
├── inputs/
│   ├── *.pdf               # Source PDFs
│   ├── style.css           # Generated CSS
│   ├── slide_template.html # Reference template
│   ├── embedding_index.json
│   └── image_index.json
└── output/
    ├── images/             # Extracted assets
    └── slides_*/           # Timestamped output
        ├── slide_1.html
        ├── slide_2.html
        └── images/         # Copied assets
```
