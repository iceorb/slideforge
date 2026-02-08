# SlideForge

SlideForge is an AI-powered pipeline that generates brand-compliant HTML presentations from PDF source materials.

## Quick Start
```bash
pip install -r slideforge/requirements.txt
cp slideforge/secrets.example.py slideforge/secrets.py
streamlit run slideforge/app.py
```

## How It Works
1. Upload brand guidelines, visual aids, and prescribing information PDFs
2. Enter a presentation topic
3. AI generates compliant slides using only approved content

## Project Structure
- `slideforge/ingestor.py` - PDF processing & asset extraction
- `slideforge/retrieval.py` - Semantic search over content
- `slideforge/planner.py` - Outline generation & content selection
- `slideforge/generator.py` - HTML slide generation
- `slideforge/app.py` - Streamlit web interface

See `slideforge/ingestion.md` and `slideforge/generation.md` for architecture diagrams.
