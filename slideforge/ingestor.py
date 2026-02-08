import os
import io
import json
import re
import base64
from pypdf import PdfReader, PdfWriter
import anthropic
import config

KNOWN_TYPES = {
    "style_guide": ["style", "brand", "guideline"],
    "visual_aid": ["visual", "aid", "core visual", "corevisual"],
    "prescribing_info": ["prescribing", "pi", "label"],
}

class Ingestor:
    def __init__(self, mock=False):
        self.mock = mock
        if not self.mock:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def extract_text(self, pdf_path, max_pages=None):
        """Extracts text from a PDF. If max_pages is set, only reads that many."""
        try:
            reader = PdfReader(pdf_path)
            pages = reader.pages[:max_pages] if max_pages else reader.pages
            text = ""
            for page in pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")
            return ""

    def classify_pdf(self, filename, pdf_path):
        """
        Classify a PDF by type. First tries filename keywords.
        Falls back to LLM (light model) reading the first page.
        Returns: 'style_guide', 'visual_aid', 'prescribing_info', or 'unknown'
        """
        lower = filename.lower()
        for doc_type, keywords in KNOWN_TYPES.items():
            if any(kw in lower for kw in keywords):
                print(f"  Classified '{filename}' as {doc_type} (by filename)")
                return doc_type

        # Filename didn't match — ask the LLM using the first page
        first_page_text = self.extract_text(pdf_path, max_pages=1)
        if not first_page_text.strip():
            print(f"  Could not extract text from first page of '{filename}', defaulting to unknown")
            return "unknown"

        if self.mock:
            return "unknown"

        try:
            response = self.client.messages.create(
                model=config.LLM_MODEL_LIGHT,
                max_tokens=50,
                system="Classify this document based on its first page. Reply with exactly one of: style_guide, visual_aid, prescribing_info, unknown",
                messages=[
                    {"role": "user", "content": f"Filename: {filename}\n\nFirst page text:\n{first_page_text[:1500]}"}
                ]
            )
            classification = response.content[0].text.strip().lower()
            # Normalize in case LLM returns something slightly off
            for valid_type in ["style_guide", "visual_aid", "prescribing_info"]:
                if valid_type in classification:
                    print(f"  Classified '{filename}' as {valid_type} (by LLM)")
                    return valid_type
            print(f"  LLM classified '{filename}' as unknown (raw: {classification})")
            return "unknown"
        except Exception as e:
            print(f"  Error classifying '{filename}': {e}")
            return "unknown"

    def _get_extension(self, data):
        """Simple magic byte detection for common image types."""
        if data.startswith(b'\xff\xd8'):
            return ".jpg"
        if data.startswith(b'\x89PNG'):
            return ".png"
        if data.startswith(b'GIF8'):
            return ".gif"
        return ".png" # Default fallback

    def extract_images(self, pdf_path, output_dir):
        """Extracts images from a PDF and saves them with correct extensions."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        image_paths = []
        try:
            reader = PdfReader(pdf_path)
            count = 0
            for page_num, page in enumerate(reader.pages):
                for image_file_object in page.images:
                    # Detect correct extension from data
                    ext = self._get_extension(image_file_object.data)
                    
                    output_filename = f"{os.path.basename(pdf_path)}_page{page_num}_{count}{ext}"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    with open(output_path, "wb") as fp:
                        fp.write(image_file_object.data)
                    
                    image_paths.append(output_path)
                    count += 1
            return image_paths
        except Exception as e:
            print(f"Error extracting images from {pdf_path}: {e}")
            return []

    def extract_images_unstructured(self, pdf_path, output_dir):
        """
        Extract images and tables from PDF using Unstructured API.
        This extracts individual visual elements rather than full-page screenshots.
        """
        from unstructured_client import UnstructuredClient
        from unstructured_client.models import shared, operations
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        image_paths = []
        
        try:
            client = UnstructuredClient(
                api_key_auth=config.UNSTRUCTURED_API_KEY,
                server_url="https://api.unstructuredapp.io"
            )
            
            print(f"  Sending PDF to Unstructured API...")
            
            with open(pdf_path, "rb") as f:
                file_content = f.read()
            
            req = operations.PartitionRequest(
                partition_parameters=shared.PartitionParameters(
                    files=shared.Files(
                        content=file_content,
                        file_name=os.path.basename(pdf_path),
                    ),
                    strategy=shared.Strategy.HI_RES,
                    extract_image_block_types=["Image", "Table"],
                    coordinates=True,
                )
            )
            
            response = client.general.partition(request=req)
            elements = response.elements or []
            
            print(f"  Received {len(elements)} elements from Unstructured")
            
            count = 0
            for elem in elements:
                elem_type = elem.get("type", "")
                
                # Check for image data in metadata
                metadata = elem.get("metadata", {})
                image_base64 = metadata.get("image_base64")
                
                if image_base64:
                    # Decode and save the image
                    import base64
                    image_data = base64.b64decode(image_base64)
                    ext = self._get_extension(image_data)
                    
                    page_num = metadata.get("page_number", 0)
                    output_filename = f"{os.path.basename(pdf_path)}_{elem_type.lower()}_p{page_num}_{count}{ext}"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    with open(output_path, "wb") as fp:
                        fp.write(image_data)
                    
                    # Store element info for later tagging
                    image_paths.append({
                        "path": output_path,
                        "type": elem_type.lower(),
                        "text": elem.get("text", ""),
                        "page": page_num,
                        "coordinates": metadata.get("coordinates", {}),
                    })
                    count += 1
                    print(f"    Saved {elem_type}: {output_filename}")
            
            print(f"  Extracted {len(image_paths)} individual assets")
            return image_paths
            
        except Exception as e:
            print(f"Error extracting with Unstructured: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _encode_image(self, image_path):
        """Base64 encode an image for Claude's vision API."""
        # Determine media type from extension
        ext = os.path.splitext(image_path)[1].lower()
        media_type = "image/png" # Default
        if ext in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"
        elif ext == ".gif":
            media_type = "image/gif"
        elif ext == ".webp":
            media_type = "image/webp"

        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return {
            "type": "base64",
            "media_type": media_type, 
            "data": data,
        }

    def tag_images(self, image_paths):
        """
        Tags images with descriptions using Claude Vision.
        For full-slide images, identifies individual elements (icons, charts, tables) within.
        Returns a list of dicts: {'path': str, 'type': str, 'label': str, 'description': str, 'elements': [...]}
        """
        results = []
        
        # Limit processing in mock mode
        if self.mock:
            return [
                {
                    "path": p, 
                    "type": "slide",
                    "label": "Mock Slide", 
                    "description": "Mock description of slide",
                    "elements": [{"type": "chart", "label": "Mock Chart", "description": "A mock chart"}]
                }
                for p in image_paths
            ]

        print(f"  Analyzing {len(image_paths)} images with Claude Vision...")
        
        for i, img_path in enumerate(image_paths):
            filename = os.path.basename(img_path)
            print(f"    [{i+1}/{len(image_paths)}] Analyzing {filename}...")
            
            try:
                # Enhanced prompt to extract individual elements from slide images
                system_prompt = """You are a visual asset cataloger for pharmaceutical presentations.
Analyze this slide image and identify ALL individual visual elements that could be reused.

For EACH distinct element you can identify (icons, charts, graphs, tables, logos, diagrams, callout boxes, stat badges, etc.), provide:
- type: one of [icon, chart, graph, table, logo, diagram, callout, stat-badge, illustration, decorative, photo]
- label: a short searchable name (2-5 words)
- description: what it shows or represents (1 sentence)
- location: where on the slide (top-left, center, bottom-right, etc.)

Return valid JSON:
{
  "slide_type": "efficacy|safety|moa|title|summary|other",
  "slide_title": "main title text if visible",
  "elements": [
    {"type": "...", "label": "...", "description": "...", "location": "..."},
    ...
  ]
}

Be thorough - identify every reusable visual element, especially:
- Medical/scientific icons
- Data visualization (KM curves, bar charts, forest plots)
- Tables with data
- Brand elements (logos, color blocks)
- Callout boxes with key stats"""

                image_source = self._encode_image(img_path)
                
                response = self.client.messages.create(
                    model=config.LLM_MODEL,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user", 
                            "content": [
                                {"type": "image", "source": image_source},
                                {"type": "text", "text": "Catalog all visual elements in this slide."}
                            ]
                        }
                    ]
                )
                
                content = response.content[0].text.strip()
                content = re.sub(r'```(?:json)?\s*', '', content)
                content = content.replace('```', '')
                
                data = json.loads(content)
                
                # Store the slide-level info
                slide_result = {
                    "path": img_path,
                    "type": data.get("slide_type", "other"),
                    "label": data.get("slide_title", filename),
                    "description": f"Slide: {data.get('slide_title', 'Untitled')}",
                    "elements": data.get("elements", [])
                }
                
                # Create searchable text from all elements
                element_texts = []
                for elem in slide_result["elements"]:
                    element_texts.append(f"{elem.get('type', '')} {elem.get('label', '')} {elem.get('description', '')}")
                slide_result["searchable_text"] = " | ".join(element_texts)
                
                results.append(slide_result)
                print(f"      Found {len(slide_result['elements'])} elements")
                
            except Exception as e:
                print(f"    Error analyzing {filename}: {e}")
                results.append({
                    "path": img_path,
                    "type": "error",
                    "label": filename,
                    "description": f"Analysis failed: {str(e)}",
                    "elements": []
                })
                
        return results

    def _encode_pdf(self, pdf_path, max_pages=None):
        """
        Base64 encode a PDF for Claude's document API.
        If max_pages is set, creates a new PDF in memory with only those pages.
        """
        if max_pages:
            try:
                reader = PdfReader(pdf_path)
                writer = PdfWriter()
                
                count = min(len(reader.pages), max_pages)
                for i in range(count):
                    writer.add_page(reader.pages[i])
                
                with io.BytesIO() as bytes_stream:
                    writer.write(bytes_stream)
                    bytes_stream.seek(0)
                    data = base64.standard_b64encode(bytes_stream.read()).decode("utf-8")
                return {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": data,
                    }
                }
            except Exception as e:
                print(f"  Warning: Could not trim PDF to {max_pages} pages: {e}. Using full file.")
                # Fallthrough to full file

        with open(pdf_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": data,
            }
        }


    def generate_css_from_guide(self, style_guide_pdf_path, slides=None):
        """
        Extracts brand colors/fonts from the style guide PDF and generates CSS.
        Passes the entire PDF directly to Claude so it can see color swatches,
        font specimens, spacing examples, and brand motifs.
        """
        if self.mock:
            return ":root { --brand-color: #00723B; --text-color: #0A2342; }"

        slides_context = ""
        if slides:
            slide_titles = [s.get("title", "") for s in slides]
            slides_context = f"\n\nThis CSS will be used for a presentation with these slides: {', '.join(slide_titles)}. Style accordingly — consider appropriate section styling, header hierarchy, and visual flow for this content."

        system_prompt = f"""You are a frontend designer specializing in pharmaceutical presentations.
You will be shown a brand style guide PDF. Study every page carefully:
- Exact brand colors (extract hex values from color swatches)
- Font families, weights, and hierarchy
- Spacing rules, border treatments, backgrounds
- Layout patterns, grid systems
- Any brand-specific design elements (circles, gradients, motifs)

Generate CSS that includes:
- **@import for Google Fonts**: Identify the brand fonts from the PDF. find the closest matching Google Fonts (e.g. Roboto, Lato, Montserrat) and include the `@import` URL at the top of the file.
- :root variables for all brand colors and fonts
- Slide container styling (1280x720px, 16:9)
- Header, body text, and content area styles
- Table, card, callout, stat-block styles matching the brand
- Any specific brand rules you can see{slides_context}
Return ONLY valid CSS, no explanation."""

        print(f"  Sending style guide PDF directly to Claude")

        try:
            response = self.client.messages.create(
                model=config.LLM_MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=[
                    {"role": "user", "content": [
                        self._encode_pdf(style_guide_pdf_path),
                        {"type": "text", "text": "Generate the CSS from this style guide."}
                    ]}
                ]
            )

            css_text = ""
            for block in response.content:
                if block.type == "text":
                    css_text = block.text
                    break
            css_text = re.sub(r'```(?:css)?\s*', '', css_text)
            css_text = css_text.replace('```', '')
            return css_text.strip()
        except Exception as e:
            print(f"Error generating CSS: {e}")
            return "/* Error generating CSS */"

    def generate_slide_template(self, css_text, visual_aid_pdf_path=None, style_guide_pdf_path=None):
        """
        Generate a reference HTML template that shows how to structure slides.
        Passes the visual aid and style guide PDFs directly - let Claude interpret them.
        """
        if self.mock:
            return """<div class="slide">
  <div class="slide-header"><h1>Slide Title</h1></div>
  <div class="slide-content"><p>Content here</p></div>
</div>"""

        # Minimal prompt - let the PDFs do the talking
        system_prompt = """You are an HTML template designer. Study the provided PDFs carefully and create a matching HTML template.

Output requirements:
- Full HTML5 document
- 1280x720px slide format
- Include descriptive comments about brand colors, assets, layout, guidelines if they are provided in the template.
- Include all style and brand content necessary to recreate the slide
- Include <style>{{ css_styles }}</style> in head
- Add CSS classes for all visual elements you observe
- Return RAW HTML only, no markdown code fences
- Try to include some comments about how to use the template, what elements could be omitted, what elements are required, etc. If we should edit some elements to fit the content, etc. but try to provide as much of a framework as possible so the downstream generation only has to do work on filling up the slide not so much the surrounding elements
"""

        user_content = []

        # Pass visual aid PDF - this is the primary design reference
        if visual_aid_pdf_path:
            print(f"  Passing visual aid PDF to Claude")
            try:
                user_content.append(self._encode_pdf(visual_aid_pdf_path, max_pages=5))
            except Exception as e:
                print(f"  Warning: could not encode visual aid PDF: {e}")

        # Pass style guide PDF - for colors, fonts, spacing rules
        if style_guide_pdf_path:
            print(f"  Passing style guide PDF to Claude")
            try:
                user_content.append(self._encode_pdf(style_guide_pdf_path, max_pages=15))
            except Exception as e:
                print(f"  Warning: could not encode style guide PDF: {e}")

        # Load extracted assets and include logos/icons in prompt
        assets_info = ""
        image_index_path = os.path.join(config.INPUT_DIR, "image_index.json")
        if os.path.exists(image_index_path):
            try:
                with open(image_index_path, "r") as f:
                    assets = json.load(f)
                
                # Find logos, icons, brand elements, and page 1 assets (logos usually there)
                key_assets = []
                for asset in assets:
                    label = asset.get("label", "").lower()
                    asset_type = asset.get("type", "").lower()
                    desc = asset.get("description", "").lower()
                    page = asset.get("page", 0)
                    
                    # Identify logos, icons, and brand elements (incl OCR variants)
                    is_brand = any(kw in label or kw in desc for kw in [
                        "logo", "brand", "icon", "fruzaqla", "fruzagla", "fruquintinib", 
                        "takeda", "capsule", "5mg", "1mg", "package"
                    ])
                    is_first_page = page == 1 or page == 0  # Page 1 usually has logo
                    
                    if is_brand or is_first_page:
                        # Normalize path to images/ for use in output folder
                        raw_path = asset.get("relative_path", asset.get("path", ""))
                        # Strip output/ prefix if present, keep just images/...
                        if raw_path.startswith("output/"):
                            normalized_path = raw_path[7:]  # Remove "output/"
                        elif raw_path.startswith("./output/"):
                            normalized_path = raw_path[9:]  # Remove "./output/"
                        else:
                            normalized_path = raw_path
                        
                        key_assets.append({
                            "path": normalized_path,
                            "label": asset.get("label", ""),
                            "description": asset.get("description", "")
                        })
                
                if key_assets:
                    assets_info = "\n\nEXTRACTED ASSETS (use these paths in the template):\n"
                    for a in key_assets[:10]:  # Limit to top 10
                        assets_info += f"- {a['label']}: {a['path']}\n  {a['description']}\n"
                    print(f"  Including {len(key_assets)} brand assets in template")
            except Exception as e:
                print(f"  Warning: could not load image index: {e}")

        user_content.append({
            "type": "text",
            "text": f"Create an HTML template matching these PDFs. Extract colors, fonts, and layout from what you see.{assets_info}\n\nInclude <img> tags for the logo and any key brand icons using the paths above."
        })

        try:
            # Use streaming for long operations with large PDFs
            html = ""
            print("  Streaming response from Claude...")
            
            with self.client.messages.stream(
                model=config.LLM_MODEL,
                max_tokens=32000,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}]
            ) as stream:
                for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == 'content_block_delta':
                            if hasattr(event.delta, 'text'):
                                html += event.delta.text
                        elif event.type == 'message_stop':
                            break
            
            print(f"  Received {len(html)} chars")
            
            if not html:
                print("  WARNING: No text received")
                return ""

            # Strip code fences if present
            match = re.search(r'```(?:html)?\s*([\s\S]*?)```', html)
            if match:
                html = match.group(1)

            result = html.strip()
            print(f"  Final template: {len(result)} chars")
            return result
            
        except Exception as e:
            print(f"Error generating slide template: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def process_inputs(self, input_dir, slides=None, specific_types=None):
        """
        Main orchestration function.
        1. Scans inputs/ for PDFs.
        2. Classifies each PDF (filename keywords, then LLM fallback).
        3. Routes to appropriate processor based on specific_types.
           If specific_types is None, processes everything.
           Options: 'style_guide', 'visual_aid', 'prescribing_info'

        slides: optional list of slide dicts from the outline, passed to CSS generation.
        """
        if specific_types is None:
            # Default to all
            specific_types = ["style_guide", "visual_aid", "prescribing_info"]
        
        print(f"Processing inputs with targets: {specific_types}")

        pi_text = ""
        style_css = ""
        image_index = []
        style_guide_pdf_path = None
        visual_aid_pdf_path = None

        # 1. Scan and Classify ALL files first to get paths
        # We need paths (like visual_aid_pdf_path) even if we aren't processing that type specifically
        files_map = []

        for filename in os.listdir(input_dir):
            path = os.path.join(input_dir, filename)
            if not filename.endswith(".pdf"):
                continue
            
            # We always classify to know what exists
            doc_type = self.classify_pdf(filename, path)
            files_map.append({"path": path, "type": doc_type, "filename": filename})
            
            if doc_type == "style_guide":
                style_guide_pdf_path = path
            elif doc_type == "visual_aid":
                visual_aid_pdf_path = path

        # 2. Process based on specific_types
        for item in files_map:
            doc_type = item["type"]
            path = item["path"]
            filename = item["filename"]

            if doc_type not in specific_types:
                continue

            print(f"Processing {filename} as {doc_type}...")

            if doc_type == "visual_aid":
                print("  Extracting images from visual aid using Unstructured API...")
                output_img_dir = os.path.join(os.path.dirname(input_dir), "output", "images")
                if not os.path.exists(output_img_dir):
                    os.makedirs(output_img_dir)
                
                # Use Unstructured API to extract individual assets
                assets = self.extract_images_unstructured(path, output_img_dir)
                
                if assets:
                    # Assets already come with type, text, page info from Unstructured
                    print("  Creating embeddings for asset retrieval...")
                    from retrieval import get_model
                    model = get_model()
                    
                    for asset in assets:
                        asset["relative_path"] = os.path.relpath(asset["path"], os.path.dirname(input_dir))
                        # Create description from type and any text
                        asset["description"] = asset.get("text", "") or f"{asset.get('type', 'image')} from page {asset.get('page', 0)}"
                        asset["label"] = f"{asset.get('type', 'asset')} page {asset.get('page', 0)}"
                        
                        # Create embedding from description + type for retrieval
                        search_text = f"{asset.get('type', '')} {asset.get('text', '')} {asset.get('description', '')}"
                        embedding = model.encode([search_text])[0]
                        asset["embedding"] = embedding.tolist()
                    
                    image_index.extend(assets)
                    print(f"  Indexed {len(assets)} individual assets with embeddings")

            elif doc_type == "prescribing_info":
                print("  Extracting content...")
                text = self.extract_text(path)
                pi_text += text + "\n"

        # 3. Generate CSS (if style_guide requested)
        if "style_guide" in specific_types and style_guide_pdf_path:
            print("Generating CSS from style guide...")
            style_css = self.generate_css_from_guide(style_guide_pdf_path, slides=slides)
            
            # Save CSS
            if style_css:
                with open(os.path.join(input_dir, "style.css"), "w") as f:
                    f.write(style_css)
                print(f"  Saved style.css")

        # 4. Generate Slide Template (if visual_aid requested)
        # Template generation needs CSS + Visual Aid
        if "visual_aid" in specific_types and visual_aid_pdf_path:
            print("Checking requirements for slide template...")
            
            # Ensure we have CSS
            if not style_css:
                css_path = os.path.join(input_dir, "style.css")
                if os.path.exists(css_path):
                    with open(css_path, "r") as f:
                        style_css = f.read()
                    print("  Loaded existing style.css")
                else:
                    print("  WARNING: No style.css found. Cannot generate slide template.")

            if style_css:
                print("Generating reference slide template...")
                template_html = self.generate_slide_template(style_css, visual_aid_pdf_path=visual_aid_pdf_path, style_guide_pdf_path=style_guide_pdf_path)
                if template_html:
                    # Save to templates directory
                    template_dir = os.path.join(os.path.dirname(__file__), "templates")
                    if not os.path.exists(template_dir):
                        os.makedirs(template_dir)
                    
                    template_path = os.path.join(template_dir, "slide.html")
                    with open(template_path, "w") as f:
                        f.write(template_html)
                    print(f"  Saved slide template to {template_path}")

        # 4. Save Outputs
        if image_index and "visual_aid" in specific_types:
            with open(os.path.join(input_dir, "image_index.json"), "w") as f:
                json.dump(image_index, f, indent=2)
            print(f"  Saved image_index.json ({len(image_index)} images)")

        if pi_text and "prescribing_info" in specific_types:
            with open(os.path.join(input_dir, "local_content.txt"), "w") as f:
                f.write(pi_text)
            print(f"  Saved local_content.txt")

            # Build embedding index for semantic retrieval
            print("Building embedding index...")
            from retrieval import build_index
            build_index(pi_text, input_dir)

        return True
