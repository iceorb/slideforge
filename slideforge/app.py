import streamlit as st
import os
import json
import shutil
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from retrieval import Retrieval
from planner import Planner
from generator import Generator
from ingestor import Ingestor
import config


# Page config
st.set_page_config(page_title="SlideForge", page_icon="📊", layout="wide")

# Title and Description
st.title("SlideForge")
st.markdown("Generate compliant HTML presentations based on approved verification content.")

# Sidebar Configuration
with st.sidebar:
    st.header("Configuration")
    mock_mode = st.toggle("Mock Mode", value=False, help="Run without live API calls (for testing)")
    
    st.divider()
    
    api_key_status = "✅ Configured" if config.ANTHROPIC_API_KEY else "❌ Missing"
    st.write(f"Anthropic Key: {api_key_status}")
    
    st.divider()
    st.divider()
    st.header("Data Ingestion")
    
    st.subheader("Update Targets")
    update_style = st.checkbox("Style Guide (CSS)", value=True)
    update_visual = st.checkbox("Visual Aid (Images & Template)", value=True)
    update_pi = st.checkbox("Prescribing Information (KB)", value=True)
    
    if st.button("Process Selected Inputs"):
        targets = []
        if update_style: targets.append("style_guide")
        if update_visual: targets.append("visual_aid")
        if update_pi: targets.append("prescribing_info")
        
        if not targets:
            st.warning("Please select at least one target to process.")
        else:
            with st.spinner(f"Processing ({', '.join(targets)})..."):
                ingestor = Ingestor(mock=mock_mode)
                ingestor.process_inputs(config.INPUT_DIR, specific_types=targets)
                st.success("Ingestion Complete!")

# Inputs Directory Setup
if not os.path.exists(config.INPUT_DIR):
    os.makedirs(config.INPUT_DIR)

# File Uploader
st.subheader("1. Upload Resources (Optional)")
uploaded_files = st.file_uploader("Upload PDFs (Style Guide, PI, Visual Aid)", accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        # Save to inputs directory
        file_path = os.path.join(config.INPUT_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
    st.success(f"Uploaded {len(uploaded_files)} files to {config.INPUT_DIR}/")

# Query Input
st.subheader("2. Define Presentation")
query = st.text_area("What should this presentation cover?", value="Create a 3-slide presentation on key efficacy and safety data", height=100)

# Generate Buttons
col1, col2 = st.columns(2)
btn_generate = col1.button("Generate Presentation", type="primary")
btn_full = col2.button("Reprocess Inputs & Generate", help="Re-ingests PDFs with slide context before generating. Use when you've uploaded new files.")

if btn_generate or btn_full:
    with st.spinner("Generating Outline..."):
        # Initialize Modules
        planner = Planner(mock=mock_mode)
        retrieval = Retrieval(mock=mock_mode)

        # We need to ensure the template dir is found correctly relative to app.py
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(current_dir, "templates")
        generator = Generator(template_dir=template_dir, mock=mock_mode)

        # 1. Plan
        outline = planner.generate_outline(query)
        if not outline.get('slides'):
             st.error("Failed to generate outline.")
             st.stop()

        st.success(f"Outline Generated: {len(outline['slides'])} slides created.")

    # 1.5. Re-ingest only if full pipeline requested
    if btn_full:
        with st.spinner("Reprocessing inputs with slide context..."):
            ingestor = Ingestor(mock=mock_mode)
            ingestor.process_inputs(config.INPUT_DIR, slides=outline.get('slides'))
            st.success("Inputs reprocessed!")

    with st.spinner("Generating slides..."):
        # Display Progress
        progress_bar = st.progress(0)

        # Store results
        generated_slides = []

        # 2. Process Slides - use timestamped folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = os.path.join(config.OUTPUT_DIR, f"slides_{timestamp}")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Copy images to output folder so slides can reference them
        images_src = os.path.join(os.path.dirname(config.INPUT_DIR), "output", "images")
        images_dst = os.path.join(output_dir, "images")
        if os.path.exists(images_src):
            shutil.copytree(images_src, images_dst, dirs_exist_ok=True)
            
        slides_list = outline.get('slides', [])

        # Phase 1: Retrieve & select content for all slides (sequential to deduplicate)
        slide_content = []
        used_content_ids = set()
        for i, slide in enumerate(slides_list):
            search_query = f"{slide['title']} {slide['topic_description']}"
            candidates = retrieval.search_claims(search_query, top_k=15)

            fresh_candidates = [c for c in candidates if c.get('id') not in used_content_ids]
            if not fresh_candidates:
                fresh_candidates = candidates[:3]

            selected_items, _ = planner.select_content_for_slide(slide['title'], fresh_candidates)

            for item in selected_items:
                used_content_ids.add(item.get('id'))

            slide_content.append(selected_items)

        # Phase 2: Generate all slides concurrently
        def generate_one(i, slide, content_items):
            filename = f"slide_{i+1}.html"
            out = os.path.join(output_dir, filename)
            generator.generate_slide_html(slide['title'], content_items, out)
            return i, slide['title'], out, filename

        results_map = {}
        with ThreadPoolExecutor(max_workers=min(len(slides_list), 5)) as executor:
            futures = {
                executor.submit(generate_one, i, slide, slide_content[i]): i
                for i, slide in enumerate(slides_list)
            }
            for future in as_completed(futures):
                i, title, out_path, fname = future.result()
                results_map[i] = {"title": title, "path": out_path, "filename": fname}
                progress_bar.progress(len(results_map) / len(slides_list))

        # Collect in slide order
        for i in range(len(slides_list)):
            generated_slides.append(results_map[i])
            
        st.success("Generation Complete!")
        
        # 3. Display Results
        st.subheader("3. Preview Slides")
        
        tabs = st.tabs([s['title'] for s in generated_slides])
        
        for i, tab in enumerate(tabs):
            slide_data = generated_slides[i]
            with tab:
                # Read HTML content
                with open(slide_data['path'], 'r') as f:
                    html_content = f.read()
                
                # Display Download Button
                with open(slide_data['path'], "rb") as file:
                    btn = st.download_button(
                        label=f"Download {slide_data['filename']}",
                        data=file,
                        file_name=slide_data['filename'],
                        mime="text/html"
                    )
                
                # Render HTML
                st.components.v1.html(html_content, height=600, scrolling=True)

    # 4. Display Assets (if available)
    image_index_path = os.path.join(config.INPUT_DIR, "image_index.json")
    if os.path.exists(image_index_path):
        st.divider()
        st.subheader("4. Extracted Assets")
        
        try:
            with open(image_index_path, "r") as f:
                assets = json.load(f)
            
            if assets:
                # Group by type
                assets_by_type = {}
                for asset in assets:
                    t = asset.get("type", "other")
                    if t not in assets_by_type:
                        assets_by_type[t] = []
                    assets_by_type[t].append(asset)
                
                # Create tabs for each type
                tabs = st.tabs([t.title() for t in assets_by_type.keys()])
                
                for i, t in enumerate(assets_by_type.keys()):
                    with tabs[i]:
                        st.caption(f"{len(assets_by_type[t])} items")
                        cols = st.columns(4)
                        for idx, asset in enumerate(assets_by_type[t]):
                            with cols[idx % 4]:
                                if os.path.exists(asset["path"]):
                                    st.image(asset["path"], output_format="PNG")
                                    st.markdown(f"**{asset.get('label', 'Asset')}**")
                                    with st.expander("Details"):
                                        st.write(asset.get("description", ""))
                                        st.caption(f"File: {os.path.basename(asset['path'])}")
                                else:
                                    st.error(f"Missing file: {asset['path']}")
            else:
                st.info("No assets found in index.")
        except Exception as e:
            st.error(f"Error loading assets: {e}")

