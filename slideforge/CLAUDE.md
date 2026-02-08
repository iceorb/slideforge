# SlideForge Pipeline

AI-powered presentation generation from PDF source materials.

## Quick Start
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files
- `ingestor.py` - PDF processing, image extraction, CSS generation
- `retrieval.py` - Semantic search over content
- `planner.py` - Outline generation & content selection  
- `generator.py` - HTML slide generation
- `app.py` - Streamlit interface

## Configuration
Copy `secrets.example.py` to `secrets.py` and add your API keys.
