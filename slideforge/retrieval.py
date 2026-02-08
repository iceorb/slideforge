import os
import json
import numpy as np
import config

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_FILE = "embedding_index.json"

# Lazy-load the model to avoid slow import on every Streamlit rerun
_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def chunk_text(text, chunk_size=500, overlap=100):
    """
    Split text into overlapping chunks by character count,
    respecting sentence boundaries where possible.
    """
    sentences = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        # Split on sentence-ending punctuation
        parts = []
        current = ""
        for char in para:
            current += char
            if char in ".!?" and len(current) > 30:
                parts.append(current.strip())
                current = ""
        if current.strip():
            parts.append(current.strip())
        sentences.extend(parts)

    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of previous chunk
            words = current_chunk.split()
            overlap_text = " ".join(words[-overlap // 5:]) if len(words) > overlap // 5 else ""
            current_chunk = overlap_text + " " + sentence
        else:
            current_chunk += " " + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Filter out tiny chunks
    return [c for c in chunks if len(c) > 40]


def build_index(text, output_dir):
    """
    Chunk text, embed each chunk, save as a local JSON index.
    Called during ingestion.
    """
    chunks = chunk_text(text)
    if not chunks:
        return []

    model = get_model()
    embeddings = model.encode(chunks, show_progress_bar=True)

    index_data = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        index_data.append({
            "id": f"chunk_{i}",
            "content": chunk,
            "embedding": emb.tolist(),
        })

    index_path = os.path.join(output_dir, INDEX_FILE)
    with open(index_path, "w") as f:
        json.dump(index_data, f)

    print(f"  Built embedding index: {len(index_data)} chunks")
    return index_data


class Retrieval:
    def __init__(self, mock=False):
        self.mock = mock
        self._index = None
        self._embeddings = None

    def _load_index(self):
        """Load the embedding index from disk."""
        if self._index is not None:
            return

        index_path = os.path.join(config.INPUT_DIR, INDEX_FILE)
        if not os.path.exists(index_path):
            self._index = []
            self._embeddings = np.array([])
            return

        with open(index_path, "r") as f:
            self._index = json.load(f)

        if self._index:
            self._embeddings = np.array([item["embedding"] for item in self._index])
        else:
            self._embeddings = np.array([])

    def search_content(self, query, top_k=5):
        """
        Embedding-based semantic search over chunked PI content.
        """
        self._load_index()

        if not self._index or self._embeddings.size == 0:
            return []

        model = get_model()
        query_embedding = model.encode([query])[0]

        # Cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        index_norms = self._embeddings / np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        similarities = index_norms @ query_norm

        # Top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < 0.1:  # Skip very low relevance
                continue
            item = self._index[idx]
            results.append({
                "id": item["id"],
                "score": score,
                "metadata": {
                    "content": item["content"],
                    "claim_text": item["content"][:300],
                    "content_type": "prescribing-info",
                }
            })

        return results

    def search_images(self, query, top_k=3):
        """
        Embedding-based search over image descriptions.
        Uses pre-computed embeddings from image_index.json.
        """
        index_path = os.path.join(config.INPUT_DIR, "image_index.json")
        if not os.path.exists(index_path):
            return []

        with open(index_path, "r") as f:
            images = json.load(f)

        if not images:
            return []

        # Check if we have pre-computed embeddings
        has_embeddings = all("embedding" in img for img in images)
        
        model = get_model()
        query_embedding = model.encode([query])[0]
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        
        if has_embeddings:
            # Use pre-computed embeddings
            desc_embeddings = np.array([img["embedding"] for img in images])
        else:
            # Fallback: compute embeddings on the fly
            descriptions = [
                f"{img.get('label', '')} {img.get('description', '')} {img.get('type', '')}"
                for img in images
            ]
            desc_embeddings = model.encode(descriptions)

        # Cosine similarity
        desc_norms = desc_embeddings / np.linalg.norm(desc_embeddings, axis=1, keepdims=True)
        similarities = desc_norms @ query_norm

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < 0.15:
                continue
            img = images[idx]
            # Use relative_path if available, otherwise fall back to path
            img_path = img.get("relative_path", img.get("path", ""))

            # Compute image dimensions from coordinates if available
            img_width, img_height = None, None
            coords = img.get("coordinates", {})
            points = coords.get("points", [])
            if len(points) == 4:
                layout_w = coords.get("layout_width", 2000)
                layout_h = coords.get("layout_height", 1500)
                # Points are in PDF pixel space — scale to slide content area (~900x525)
                px_w = abs(points[2][0] - points[0][0])
                px_h = abs(points[2][1] - points[0][1])
                # Scale relative to PDF page size → slide content area
                img_width = int(px_w / layout_w * 900)
                img_height = int(px_h / layout_h * 525)

            meta = {
                "path": img_path,
                "label": img.get("label", ""),
                "type": img.get("type", ""),
                "content": f"Image: {img.get('description', '')}",
                "content_type": "visual-aid",
            }
            if img_width and img_height:
                meta["img_width"] = img_width
                meta["img_height"] = img_height

            results.append({
                "id": f"img_{os.path.basename(img_path)}",
                "score": score,
                "metadata": meta,
            })

        return results

    def search_claims(self, query, top_k=5):
        """
        Combined semantic search: PI content + images.
        """
        if self.mock:
            return [{
                "id": "mock_1",
                "score": 1.0,
                "metadata": {
                    "claim_text": "Mock claim about 8.6 months mPFS",
                    "content": "Mock PI content about efficacy.",
                    "content_type": "mock",
                }
            }]

        results = []
        results.extend(self.search_content(query, top_k=top_k))
        results.extend(self.search_images(query, top_k=3))

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k + 3]
