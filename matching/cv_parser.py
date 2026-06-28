import json
import re
from pathlib import Path

try:
    import pdfminer.high_level as pdfminer
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

CV_DIR = Path(__file__).parent.parent / "cv"
PARSED_PATH = CV_DIR / "cv_parsed.json"

SKILL_KEYWORDS = [
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "sql",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "machine learning", "deep learning", "nlp", "computer vision", "llm",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "react", "fastapi", "django", "flask", "node.js",
    "networking", "cisco", "firewalls", "penetration testing", "cyber security",
    "devops", "ci/cd", "jenkins", "github actions",
    "data analysis", "tableau", "power bi", "excel",
    "product management", "agile", "scrum", "jira",
    "finance", "accounting", "bloomberg", "financial modelling",
    "marketing", "seo", "google analytics", "social media",
    "business analysis", "requirements gathering", "stakeholder management"
]


def extract_text_from_pdf(pdf_path: Path) -> str:
    if not PDF_AVAILABLE:
        raise ImportError("pdfminer not installed. Run: pip install pdfminer.six")
    return pdfminer.extract_text(str(pdf_path))


def extract_skills(text: str) -> list:
    text_lower = text.lower()
    found = [skill for skill in SKILL_KEYWORDS if skill in text_lower]
    return list(set(found))


def extract_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]+", text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    match = re.search(r"(\+?\d[\d\s\-().]{7,20})", text)
    return match.group(0).strip() if match else ""


def parse_cv() -> dict:
    pdf_files = list(CV_DIR.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError("No PDF found in cv/ folder. Please add your CV.")

    pdf_path = pdf_files[0]
    print(f"  Parsing CV: {pdf_path.name}")

    raw_text = extract_text_from_pdf(pdf_path)
    skills = extract_skills(raw_text)

    parsed = {
        "raw_text": raw_text,
        "skills": skills,
        "email": extract_email(raw_text),
        "phone": extract_phone(raw_text),
        "word_count": len(raw_text.split()),
        "cv_file": pdf_path.name
    }

    PARSED_PATH.write_text(json.dumps(parsed, indent=2))
    print(f"  Extracted {len(skills)} skills")
    return parsed


def load_parsed_cv() -> dict:
    if PARSED_PATH.exists():
        return json.loads(PARSED_PATH.read_text())
    return parse_cv()
