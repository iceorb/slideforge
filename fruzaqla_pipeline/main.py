import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from retrieval import Retrieval
from planner import Planner
from generator import Generator
import config

def main():
    parser = argparse.ArgumentParser(description="Fruzaqla Presentation Generator")
    parser.add_argument("--query", type=str, required=True, help="User query for the presentation")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without API calls")
    args = parser.parse_args()

    # Ensure output directory exists
    if not os.path.exists(config.OUTPUT_DIR):
        os.makedirs(config.OUTPUT_DIR)

    print(f"Processing query: {args.query}")
    if args.mock:
        print("WARNING: Running in MOCK mode.")

    # 1. Plan Outline
    planner = Planner(mock=args.mock)
    print("Generating outline...")
    outline = planner.generate_outline(args.query)
    slides_list = outline.get('slides', [])
    print(f"Outline generated: {[s['title'] for s in slides_list]}")

    # 2. Retrieve & Select Content (sequential for deduplication)
    retrieval = Retrieval(mock=args.mock)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, "templates")
    generator = Generator(template_dir=template_dir, mock=args.mock)

    slide_content = []
    used_content_ids = set()
    for i, slide in enumerate(slides_list):
        print(f"Retrieving content for Slide {i+1}: {slide['title']}")
        search_query = f"{slide['title']} {slide['topic_description']}"
        candidates = retrieval.search_claims(search_query, top_k=15)

        fresh_candidates = [c for c in candidates if c.get('id') not in used_content_ids]
        if not fresh_candidates:
            fresh_candidates = candidates[:3]

        selected_items, _ = planner.select_content_for_slide(slide['title'], fresh_candidates)
        for item in selected_items:
            used_content_ids.add(item.get('id'))
        slide_content.append(selected_items)
        print(f"  Selected {len(selected_items)} items.")

    # 3. Generate slides concurrently
    print(f"\nGenerating {len(slides_list)} slides concurrently...")
    slide_files = [None] * len(slides_list)

    def generate_one(i, slide, content_items):
        filename = f"slide_{i+1}.html"
        output_path = os.path.join(config.OUTPUT_DIR, filename)
        generator.generate_slide_html(slide['title'], content_items, output_path)
        return i, output_path

    with ThreadPoolExecutor(max_workers=min(len(slides_list), 5)) as executor:
        futures = {
            executor.submit(generate_one, i, slide, slide_content[i]): i
            for i, slide in enumerate(slides_list)
        }
        for future in as_completed(futures):
            i, output_path = future.result()
            slide_files[i] = output_path
            print(f"  Generated slide {i+1}: {output_path}")

    print("\nSuccess! Generated slides:")
    for f in slide_files:
        print(f" - {f}")

if __name__ == "__main__":
    main()
