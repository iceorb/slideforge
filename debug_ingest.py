import os
import sys

# Ensure we can import from the pipeline
sys.path.append(os.path.abspath("fruzaqla_pipeline"))

from ingestor import Ingestor
import config

# Setup
INPUT_DIR = config.INPUT_DIR
print(f"Checking input dir: {INPUT_DIR}")
if not os.path.exists(INPUT_DIR):
    print("Input dir does not exist!")
    sys.exit(1)

# Initialize Ingestor
print("Initializing Ingestor...")
ingestor = Ingestor(mock=False)

# 1. Check file classification
style_guide_path = None
visual_aid_path = None

print("\n--- Checking Files ---")
for filename in os.listdir(INPUT_DIR):
    if not filename.endswith(".pdf"):
        continue
    path = os.path.join(INPUT_DIR, filename)
    print(f"Checking {filename}...")
    doc_type = ingestor.classify_pdf(filename, path)
    print(f"  Result: {doc_type}")
    
    if doc_type == "style_guide":
        style_guide_path = path
    elif doc_type == "visual_aid":
        visual_aid_path = path

# 2. Try to generate CSS and Template
if style_guide_path:
    print(f"\n--- Generating CSS from {style_guide_path} ---")
    try:
        style_css = ingestor.generate_css_from_guide(style_guide_path)
        print(f"CSS generated length: {len(style_css)}")
        if len(style_css) < 100:
            print("CSS seems too short/invalid:" + style_css)
        
        if style_css:
            print("\n--- Generating Slide Template ---")
            try:
                template_html = ingestor.generate_slide_template(style_css, visual_aid_pdf_path=visual_aid_path)
                print(f"Template generated length: {len(template_html)}")
                if not template_html:
                    print("Template HTML is empty!")
            except Exception as e:
                print(f"EXCEPTION in generate_slide_template: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        print(f"EXCEPTION in generate_css_from_guide: {e}")
        import traceback
        traceback.print_exc()

else:
    print("\nNo style guide found! Cannot generate template.")
