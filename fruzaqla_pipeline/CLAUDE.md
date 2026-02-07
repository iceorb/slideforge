# FRUZAQLA Presentation Pipeline

## Overview
Generates HTML slides for pharmaceutical presentations from PDFs. Uses Claude for content generation and Unstructured API for asset extraction.

## Architecture

### Input Processing (`ingestor.py`)
- **PDF Classification**: Auto-classifies PDFs as `style_guide`, `visual_aid`, or `prescribing_info`
- **Asset Extraction**: Uses Unstructured API (hi_res) to extract individual images/tables
- **CSS Generation**: Generates brand CSS from style guide PDFs via Claude Vision
- **Template Generation**: Creates `slide_template.html` with embedded logo paths and brand styling

### Retrieval System (`retrieval.py`)
- **Embedding Index**: Chunks and embeds PI text for semantic search
- **Image Search**: Searches assets by description/embedding
- **Combined Search**: `search_claims()` returns both PI content and visual assets

### Slide Generation (`generator.py`)
- Generates HTML slides using the full template + previous slide for consistency
- Passes available images with paths so Claude can embed `<img>` tags
- Outputs to timestamped folders: `output/slides_YYYYMMDD_HHMM/`

## Key Files
```
config.py          - API keys (Anthropic, Unstructured)
ingestor.py        - PDF processing, CSS/template generation
retrieval.py       - Semantic search (content + images)
generator.py       - HTML slide generation with LLM
planner.py         - Outline generation and content selection
app.py             - Streamlit UI
templates/slide.html - Jinja2 wrapper template
```

## Data Flow
```
1. PDFs → ingestor.py → inputs/
   - style.css (brand CSS)
   - slide_template.html (reference template with logo paths)
   - embedding_index.json (PI text chunks + embeddings)
   - image_index.json (extracted assets + embeddings)

2. output/images/ → extracted individual assets (charts, logos, tables)

3. User prompt → planner.py → slide outline
   → retrieval.py → relevant PI content + images
   → generator.py → output/slides_*/slide_*.html
```

## Asset Handling
- **Extraction**: Unstructured API extracts images/tables with coordinates
- **Filtering**: Template includes page 1 assets + brand keywords (logo, fruzaqla, capsule, etc.)
- **Generation**: Each slide receives available images with paths for embedding
- **Consistency**: Previous slide HTML passed to maintain layout across deck

## Commands
```bash
# Run the app
python3 -m streamlit run fruzaqla_pipeline/app.py

# Process inputs manually
python3 -c "from ingestor import Ingestor; Ingestor().process_inputs('inputs')"
```

## API Keys (in config.py)
- **ANTHROPIC_API_KEY**: Claude for generation and vision
- **UNSTRUCTURED_API_KEY**: Asset extraction from PDFs
