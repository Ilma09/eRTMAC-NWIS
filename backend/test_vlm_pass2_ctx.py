"""
test_vlm_pass2_ctx.py
Probes Pass 2's actual context requirement (full page text transcription + NPT
hazard extraction), which is a much larger prompt+output than Pass 1's 5-field
header JSON. Prints prompt_eval_count / eval_count from Ollama so we can pick a
real num_ctx value for config.py instead of reusing Pass 1's 8192 blindly.

Uses TESTDOC_p2_full.png - has a data table, a supplementary-notes block (~30
lines), and an explicit mentioned hazard ("Lost circulation... at 1,800m"), so
it's representative of a realistic worst-case Pass 2 page.
"""
import sys
import time

import ollama

PAGE_IMAGE = "pages/TESTDOC_p2_full.png"
MODEL = "qwen2.5vl:3b"
TRY_NUM_CTX = 16384  # generous ceiling for this probe; we'll size down after seeing real usage

PROMPT = """You are looking at one page of a scanned Well Completion Report (WCR).
Scan quality may be poor - some characters may be missing, faded, or corrupted.

1. Transcribe the full readable text content of this page (tables and prose).
2. Identify any Non-Productive Time (NPT) hazards mentioned on this page
   (e.g. Stuck Pipe, Lost Circulation, Gas Kick, Washout), each with its depth
   in meters if stated, and a confidence (HIGH, MEDIUM, LOW) for the depth reading.

Respond with ONLY a JSON object in this exact shape, no other text:
{
  "page_text": "...",
  "hazards": [
    {"hazard_type": "...", "depth_m": {"value": ..., "confidence": "..."}, "description": "..."}
  ]
}
If no hazards are mentioned, use an empty array for "hazards"."""


def main():
    print(f"Model: {MODEL}")
    print(f"Image: {PAGE_IMAGE}")
    print(f"Requested num_ctx ceiling: {TRY_NUM_CTX}")
    print("-" * 70)

    start = time.time()
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT, "images": [PAGE_IMAGE]}],
        options={"num_ctx": TRY_NUM_CTX},
    )
    elapsed = time.time() - start

    raw_text = response["message"]["content"]
    prompt_tokens = response.get("prompt_eval_count")
    output_tokens = response.get("eval_count")
    total = (prompt_tokens or 0) + (output_tokens or 0)

    print(f"Elapsed: {elapsed:.1f}s")
    print(f"prompt_eval_count (input tokens incl. image): {prompt_tokens}")
    print(f"eval_count (output tokens): {output_tokens}")
    print(f"TOTAL tokens used: {total}")
    print("-" * 70)
    print("RAW MODEL OUTPUT:")
    print("-" * 70)
    print(raw_text)
    print("-" * 70)


if __name__ == "__main__":
    sys.exit(main())
