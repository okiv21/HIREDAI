"""
build_structured_cv.py — One-off utility to convert your existing CV PDF
into the structured cv_structured.json format that cv_tailor.py needs.

Run this once after adding your CV:
    python matching/build_structured_cv.py

It extracts text from cv/my_cv.pdf, sends it to the LLM with a strict
extraction prompt, and saves cv/cv_structured.json.

Review the output afterwards — extraction can occasionally miss or
misplace a bullet point, and it's your CV, so a quick manual check
is worth it before this becomes the source of truth for every
tailored application.
"""

import os
import json
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from matching.cv_parser import extract_text_from_pdf

CV_DIR = Path(__file__).parent.parent / "cv"
OUTPUT_PATH = CV_DIR / "cv_structured.json"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

EXTRACTION_PROMPT = """
Convert the following CV text into a structured JSON object with this EXACT schema:

{{
  "name": "",
  "contact": {{ "email": "", "phone": "", "location": "", "linkedin": "", "github": "" }},
  "summary": "",
  "skills": [],
  "experience": [
    {{ "title": "", "company": "", "dates": "", "bullets": [] }}
  ],
  "projects": [
    {{ "name": "", "description": "", "bullets": [] }}
  ],
  "education": [
    {{ "degree": "", "institution": "", "dates": "" }}
  ]
}}

RULES:
- Extract ONLY what is actually present in the text below. Do not add or infer anything.
- If a field isn't present, leave it as an empty string or empty list.
- Preserve bullet points as separate list items, not merged into one string.
- Return ONLY the JSON object, no markdown, no explanation.

CV TEXT:
{cv_text}
"""


def build_structured_cv():
    pdf_files = list(CV_DIR.glob("*.pdf"))
    if not pdf_files:
        print("No PDF found in cv/ folder. Add your CV first (cv/my_cv.pdf).")
        return

    print(f"Reading {pdf_files[0].name}...")
    raw_text = extract_text_from_pdf(pdf_files[0])

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("GROQ_API_KEY not set in environment. Add it to .env first.")
        return

    print("Extracting structured data via LLM...")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(cv_text=raw_text[:6000])}],
        "max_tokens": 2500,
        "temperature": 0.1,
    }

    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=40)
    resp.raise_for_status()
    raw_output = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip code fences if present
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]
    raw_output = raw_output.strip()

    try:
        structured = json.loads(raw_output)
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM output as JSON: {e}")
        print("Raw output saved to cv/cv_structured_raw.txt for manual review.")
        (CV_DIR / "cv_structured_raw.txt").write_text(raw_output)
        return

    OUTPUT_PATH.write_text(json.dumps(structured, indent=2))
    print(f"\nSaved: {OUTPUT_PATH}")
    print("Please review this file manually — extraction can miss details.")
    print("Compare it against cv/cv_structured.example.json for the expected format.")


if __name__ == "__main__":
    build_structured_cv()
