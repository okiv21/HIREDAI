import os
import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def _cv_context(structured_cv: dict | None) -> str:
    """Flatten the parts of the structured CV that help answer questions —
    skills and a few experience/project highlights — into a compact brief."""
    if not structured_cv:
        return ""

    lines = []
    skills = structured_cv.get("skills", [])
    if skills:
        lines.append("Skills: " + ", ".join(skills[:25]))

    for exp in structured_cv.get("experience", [])[:3]:
        title = exp.get("title", "")
        company = exp.get("company", "")
        dates = exp.get("dates", "")
        header = " — ".join(p for p in [title, company, dates] if p)
        if header:
            lines.append(f"Experience: {header}")
        for b in exp.get("bullets", [])[:2]:
            lines.append(f"  • {b}")

    for proj in structured_cv.get("projects", [])[:2]:
        name = proj.get("name", "")
        if name:
            lines.append(f"Project: {name}")

    edu = structured_cv.get("education", [])
    if edu:
        e = edu[0]
        lines.append(
            "Education: " + " — ".join(
                p for p in [e.get("degree", ""), e.get("institution", "")] if p
            )
        )
    return "\n".join(lines)


def generate_answer(question: str, job: dict, structured_cv: dict = None) -> str:
    """Generate a tailored answer to a job application question using the
    applicant's actual CV details."""
    name = (structured_cv or {}).get("name", "")
    about = (structured_cv or {}).get("summary", "")
    cv_brief = _cv_context(structured_cv)

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return about

    prompt = f"""
You are filling in a job application form ON BEHALF OF the applicant below.
Answer the question in the applicant's own voice (first person), using ONLY
facts present in their CV details. Never invent experience, numbers, or skills
they don't have. If the CV doesn't support an answer, give a brief honest one.

Question: "{question}"

APPLICANT
- Name: {name}
- Summary: {about}
{cv_brief}

ROLE
- {job.get('title', '')} at {job.get('company', '')}
- Skills the CV matches for this role: {', '.join(job.get('matched_skills', []))}

Rules:
- Max 3 sentences (1 sentence for simple factual questions)
- Specific and grounded in the CV, not generic
- First person, no fluff, no placeholders like [Name]
- Return only the answer text, nothing else
"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.6
    }
    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [answer_gen] Failed: {e}")
        return about