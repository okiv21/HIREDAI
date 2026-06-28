import os
import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def generate_cover_letter(job: dict, cv_summary: str, structured_cv: dict = None) -> str:
    """
    cv_summary: a flat text summary of the user's skills/experience (used as
    fallback context if structured_cv isn't provided).
    structured_cv: the user's full structured CV dict (name, summary, skills,
    experience, projects) — preferred when available, since it gives the LLM
    real detail instead of just a skills list.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return "[No GROQ_API_KEY configured on the server — cover letter not generated. Write your own here.]"

    name = (structured_cv or {}).get("name", "")
    about = (structured_cv or {}).get("summary", cv_summary)

    prompt = f"""
Write a concise, professional cover letter for this job application.

Applicant: {name}
About: {about}
Skills matched: {', '.join(job.get('matched_skills', []))}

Job Title: {job['title']}
Company: {job['company']}
Job Description (excerpt):
{job.get('description', '')[:800]}

Instructions:
- 3 short paragraphs max
- First paragraph: enthusiasm for the role and company
- Second paragraph: 2-3 specific skills/experiences that match the job
- Third paragraph: call to action
- Professional but not robotic
- Do NOT use generic phrases like "I am writing to apply"
- Do NOT include placeholders like [Your Name]
- Sign off with: {name}
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.7
    }

    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [cover_letter] Generation failed: {e}")
        return f"[Cover letter generation failed: {e}. Edit this box to write your own before submitting.]"