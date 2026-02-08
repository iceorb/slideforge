# Slideforge, 

Companies spend upwards of $500,000-$1,000,000 annually on marketing slide production—cycling through agencies, compliance reviews, and endless revision rounds. SlideForge collapses that workflow into minutes. Upload your brand guidelines, prescribing information, and visual assets once. From there, every presentation is generated on-demand: on-brand, on-label, and ready for MLR. 

<img width="1024" height="547" alt="image" src="https://github.com/user-attachments/assets/11f2f942-aac6-478f-b8bf-7dc78aabe9b2" />


* Important information redacted.

## Features

- **PDF Ingestion**: Automatically classifies and processes Style Guides, Visual Aids, and Prescribing Information
- **Brand Extraction**: Extracts colors, fonts, and design patterns from style guides to generate CSS
- **Image Extraction**: Uses Unstructured API to extract images and tables from visual aids
- **Semantic Search**: Embedding-based retrieval of relevant content for each slide
- **Compliant Generation**: LLM selects only from approved content (no hallucination)
- **Streamlit UI**: Web interface for uploading files and previewing slides
## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r fruzaqla_pipeline/requirements.txt
   ```

2. **Configure API Keys**:
   ```bash
   cp fruzaqla_pipeline/secrets.example.py fruzaqla_pipeline/secrets.py
   # Edit secrets.py with your API keys
   ```

   Required keys:
   - `ANTHROPIC_API_KEY` - For Claude LLM
   - `UNSTRUCTURED_API_KEY` - For PDF image extraction

## Usage

### Streamlit App (Recommended)
```bash
streamlit run fruzaqla_pipeline/app.py
```

### Command Line
```bash
python3 fruzaqla_pipeline/main.py --query "Create a 5-slide presentation on efficacy"
```

### Mock Mode (No API keys)
```bash
python3 fruzaqla_pipeline/main.py --query "Test query" --mock
```

## Project Structure

```
fruzaqla_pipeline/
├── app.py           # Streamlit web interface
├── config.py        # Configuration (imports secrets)
├── ingestor.py      # PDF processing & asset extraction
├── retrieval.py     # Semantic search over content
├── planner.py       # Outline generation & content selection
├── generator.py     # HTML slide generation
├── ingestion.md     # Pipeline documentation
├── generation.md    # Pipeline documentation
└── templates/       # Jinja2 slide templates
```

## How It Works

1. **Ingest**: Upload PDFs → classify by type → extract text/images → build embedding index
2. **Plan**: User query → LLM generates slide outline with titles and topics
3. **Retrieve**: For each slide → semantic search finds relevant approved content
4. **Select**: LLM picks best content pieces (compliance constraint)
5. **Generate**: LLM creates HTML using brand template + selected content

See `ingestion.md` and `generation.md` for detailed architecture diagrams.

## Output

Generated slides are saved to `output/slides_YYYYMMDD_HHMM/` as standalone HTML files.
