import os
import re
import anthropic
import config


def extract_text_from_response(response):
    """Extract text content from a Claude response, skipping thinking blocks."""
    texts = []
    for block in response.content:
        if block.type == "text" and block.text.strip():
            texts.append(block.text)
    if not texts:
        block_types = [block.type for block in response.content]
        raise ValueError(f"No text blocks in response. Block types: {block_types}")
    return "\n".join(texts)


def extract_html(text):
    """Extract HTML from LLM response, stripping code fences."""
    match = re.search(r'```(?:html)?\s*([\s\S]*?)```', text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _normalize_image_path(path):
    """Normalize image paths to be relative to the slide output folder."""
    if path.startswith("output/"):
        return path[7:]
    if path.startswith("./output/"):
        return path[9:]
    return path


class Generator:
    def __init__(self, template_dir="templates", mock=False):
        self.template_dir = template_dir
        self.mock = mock
        if not self.mock:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._template_cache = None
        self._css_cache = None

    def _load_css(self):
        """Load the generated style.css if available."""
        if self._css_cache is not None:
            return self._css_cache
        style_path = os.path.join(config.INPUT_DIR, "style.css")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self._css_cache = f.read()
                return self._css_cache
        self._css_cache = ""
        return ""

    def _load_slide_template(self):
        """
        Load the reference slide template generated during ingestion.
        This is a complete branded HTML slide used as a design reference for the LLM.
        """
        if self._template_cache is not None:
            return self._template_cache

        # Check templates/ dir first (where ingestor saves it), then inputs/
        template_path = os.path.join(self.template_dir, "slide.html")
        if not os.path.exists(template_path):
            template_path = os.path.join(config.INPUT_DIR, "slide_template.html")

        if os.path.exists(template_path):
            with open(template_path, "r") as f:
                content = f.read()
            # Normalize image paths for slides in output folder
            content = content.replace('src="output/images/', 'src="images/')
            content = content.replace('src="./output/images/', 'src="images/')
            # Inject CSS if template has the placeholder
            css = self._load_css()
            if css and '{{ css_styles }}' in content:
                content = content.replace('{{ css_styles }}', css)
            self._template_cache = content
            return content

        self._template_cache = ""
        return ""

    def _generate_slide(self, slide_title, content_items, slide_template):
        """
        Use LLM to generate a COMPLETE HTML slide based on the brand template.
        The template is a full branded slide — the LLM adapts it with the approved content.
        """
        # Separate text content from image assets
        content_parts = []
        image_assets = []

        for i, item in enumerate(content_items):
            meta = item.get('metadata', item)
            content_type = meta.get('content_type', 'text')

            if content_type == 'visual-aid':
                asset = {
                    "path": _normalize_image_path(meta.get('path', meta.get('relative_path', ''))),
                    "label": meta.get('label', ''),
                    "description": meta.get('content', ''),
                }
                if meta.get('img_width') and meta.get('img_height'):
                    asset["width"] = meta["img_width"]
                    asset["height"] = meta["img_height"]
                image_assets.append(asset)
            else:
                content_parts.append(
                    f"Content {i+1} (type: {content_type}):\n{meta.get('content', meta.get('claim_text', ''))}"
                )

        content_context = "\n---\n".join(content_parts) if content_parts else "No text content available."

        # Build image context
        image_context = ""
        if image_assets:
            image_lines = []
            for img in image_assets:
                size_info = ""
                if img.get('width') and img.get('height'):
                    size_info = f"\n  Approx size on slide: {img['width']}x{img['height']}px"
                image_lines.append(f"- Image: {img['path']}\n  Label: {img['label']}\n  Description: {img['description']}{size_info}")
            image_context = (
                f"\n\nAVAILABLE IMAGES (use <img src='...' alt='...'> to include):\n"
                f"The content area is ~900x525px. If an image is tall, reduce text accordingly.\n"
                + "\n".join(image_lines)
            )

        system_prompt = f"""You are an expert HTML slide designer for pharmaceutical presentations.
You will be given a REFERENCE TEMPLATE (a complete branded HTML slide) and APPROVED CONTENT.
Generate a COMPLETE HTML slide document that:

1. Copies the template's full HTML structure — <!DOCTYPE>, <html>, <head>, <style>, <body>, everything
2. Keeps ALL chrome elements: top banner, logo, ISI sidebar, bottom nav bar, nav arrows, footnote area
3. Replaces ONLY the main content area (.content-area) with the approved content below
4. Sets the headline to: {slide_title}
5. Image paths should be relative (e.g. images/filename.jpg)

Rules:
- Return a COMPLETE HTML document — copy the full structure from the template
- The main content MUST come from the "Approved Content" — NOT from the template's example text
- Keep the ISI safety text, logo, navigation bar exactly as they are in the template
- Limit bullet points to 4-5 maximum
- If including an image, reduce text accordingly
- Return RAW HTML only, no markdown code fences

--- REFERENCE TEMPLATE ---
{slide_template}
--- END TEMPLATE ---"""

        user_prompt = f"APPROVED CONTENT FOR THIS SLIDE (use this, not template text):\n{content_context}{image_context}"

        try:
            response = self.client.messages.create(
                model=config.LLM_MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            html = extract_text_from_response(response)
            return extract_html(html)
        except Exception as e:
            print(f"Error generating slide HTML: {e}")
            return self._fallback_slide(slide_title, content_items)

    def _fallback_slide(self, slide_title, content_items):
        """Basic fallback slide when LLM fails."""
        parts = []
        for item in content_items:
            meta = item.get('metadata', item)
            if meta.get('content_type') == 'visual-aid':
                path = _normalize_image_path(meta.get('path', meta.get('relative_path', '')))
                parts.append(f"<div><img src='{path}' alt='{meta.get('label', '')}' style='max-width:100%;height:auto;'></div>")
            else:
                text = meta.get('content', meta.get('claim_text', ''))
                parts.append(f"<p>{text}</p>")
        body = ''.join(parts) or '<p>Content unavailable</p>'
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body {{ font-family: sans-serif; margin: 40px; }}
</style></head><body>
<h1>{slide_title}</h1>
{body}
</body></html>"""

    def generate_slide_html(self, slide_title, content_items, output_path):
        """
        Generates a single HTML slide.
        The LLM produces a complete HTML document based on the brand template.
        """
        slide_template = self._load_slide_template()

        if self.mock or not content_items:
            html = self._fallback_slide(slide_title, content_items or [])
        elif not slide_template:
            print(f"  WARNING: No slide template found. Generating without brand reference.")
            html = self._fallback_slide(slide_title, content_items)
        else:
            html = self._generate_slide(slide_title, content_items, slide_template)

        with open(output_path, "w") as f:
            f.write(html)

        return output_path
