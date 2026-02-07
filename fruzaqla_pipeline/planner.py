import anthropic
import config
import json
import re

def extract_text_from_response(response):
    """Extract all text content from a Claude response, skipping thinking blocks."""
    texts = []
    for block in response.content:
        if block.type == "text" and block.text.strip():
            texts.append(block.text)
    if not texts:
        # Debug: show what block types we got
        block_types = [block.type for block in response.content]
        raise ValueError(f"No text blocks in response. Block types: {block_types}")
    return "\n".join(texts)

def extract_json(text):
    """Strip markdown code fences and extract JSON from LLM response."""
    # Try to find JSON in code fences first
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        text = match.group(1)
    # Try to find a JSON object in the text
    if not text.strip().startswith('{'):
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            text = match.group(0)
    return json.loads(text.strip())

class Planner:
    def __init__(self, mock=False):
        self.mock = mock
        if not self.mock:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def generate_outline(self, user_query):
        """
        Generates a list of slide titles/topics based on the user query.
        The LLM determines the appropriate number of slides from the prompt.
        """
        if self.mock:
            return {
                "slides": [
                    {"title": f"Slide {i+1}: Mock Topic", "topic_description": "Mock description for testing pipeline."}
                    for i in range(3)
                ]
            }

        system_prompt = """
        You are an expert presentation planner for a pharmaceutical brand "Fruzaqla".
        Based on the user's request, determine the appropriate number of slides and create an outline.
        If the user specifies a number of slides, use that. Otherwise, choose a reasonable number (typically 3-7) based on the breadth of the topic.
        Return a JSON object with a key "slides" containing a list of objects, each with "title" and "topic_description".
        The "topic_description" should be detailed enough to search for content.
        Example: { "slides": [ { "title": "Efficacy Overview", "topic_description": "Key efficacy statistics and study results for Fruzaqla" } ] }
        """

        try:
            response = self.client.messages.create(
                model=config.LLM_MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_query}
                ]
            )
            
            json_text = extract_text_from_response(response)
            return extract_json(json_text)
        except Exception as e:
            print(f"Error parsing outline: {e}")
            return {"slides": []}

    def select_content_for_slide(self, slide_topic, retrieved_items):
        """
        Selects the best matching content from retrieved items for a specific slide.
        Enforces the "Approved Content" constraint by only selecting from what is provided.
        """
        if self.mock:
            # Return all items in mock mode or a subset
            return retrieved_items[:2], "Mock layout suggestion"

        # Prepare context from retrieved items
        context_str = ""
        for i, item in enumerate(retrieved_items):
            meta = item['metadata']
            context_str += f"Item {i}:\nID: {item['id']}\nText: {meta.get('claim_text', '')}\nContent: {meta.get('content', '')}\nType: {meta.get('content_type', '')}\n---\n"

        system_prompt = """
        You are a compliance officer and content assembler.
        Your goal is to select the BEST pieces of approved content for a slide.
        You MUST ONLY use the provided retrieved items. Do not invent new text.
        Select items that are relevant to the slide topic.
        Return a JSON object with "selected_item_ids" (list of IDs) and "layout_suggestion" (string).
        """

        user_prompt = f"Slide Topic: {slide_topic}\n\nAvailable Approved Content:\n{context_str}"

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
            
            json_text = extract_text_from_response(response)
            result = extract_json(json_text)

            # Map IDs back to full items
            selected_items = []
            id_map = {item['id']: item for item in retrieved_items}
            for pid in result.get('selected_item_ids', []):
                if pid in id_map:
                    selected_items.append(id_map[pid])
            return selected_items, result.get('layout_suggestion', '')
        except Exception as e:
            print(f"Error selecting content: {e}")
            return [], ""
