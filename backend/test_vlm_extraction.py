"""
test_vlm_extraction.py
Standalone probe: send ONE already-rasterized page PNG to qwen2.5vl:3b via Ollama
and print the raw model output. No parsing, no validation, no retry logic.

Purpose: see real extraction quality/behavior on a degraded scan BEFORE designing
unified_parser.py's confidence-scoring prompt. Do not build on top of this until
the raw output below has been reviewed.
"""
import sys
import time

import ollama

PAGE_IMAGE = "pages/TESTDOC_p1_full.png"
MODEL = "qwen2.5vl:3b"

PROMPT = """You are looking at page 1 of a scanned Well Completion Report (WCR).
The scan quality is poor - some characters may be missing, faded, or corrupted.

Extract the following fields as JSON. For each field, also state your confidence
(HIGH, MEDIUM, or LOW) based on how legible that specific piece of text was.
If a field is not present or fully illegible, use null for the value and LOW for confidence.
Do not guess or invent a value you cannot actually read.

Fields to extract:
- well_name (the Well ID)
- operator (company name)
- field_location (the FIELD: line, e.g. a place name)
- total_depth_m (numeric, from the table if present on this page, else null)
- well_status_type (e.g. "Oil Producer", "Gas Producer", "Dry")

Respond with ONLY a JSON object in this exact shape, no other text:
{
  "well_name": {"value": ..., "confidence": ...},
  "operator": {"value": ..., "confidence": ...},
  "field_location": {"value": ..., "confidence": ...},
  "total_depth_m": {"value": ..., "confidence": ...},
  "well_status_type": {"value": ..., "confidence": ...}
}"""


def main():
    print(f"Model: {MODEL}")
    print(f"Image: {PAGE_IMAGE}")
    print(f"Prompt length: {len(PROMPT)} chars")
    print("-" * 70)

    start = time.time()
    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": PROMPT,
                "images": [PAGE_IMAGE],
            }
        ],
        options={"num_ctx": 8192},
    )
    elapsed = time.time() - start

    raw_text = response["message"]["content"]

    print(f"Elapsed: {elapsed:.1f}s")
    print("-" * 70)
    print("RAW MODEL OUTPUT:")
    print("-" * 70)
    print(raw_text)
    print("-" * 70)


if __name__ == "__main__":
    sys.exit(main())
