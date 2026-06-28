import json
import numpy as np
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

EMBEDDING_PATH = Path(__file__).parent.parent / "cv" / "cv_embedding.npy"
MODEL_NAME = "all-MiniLM-L6-v2"  # fast, free, good quality

_model = None


def get_model():
    global _model
    if _model is None:
        if not ST_AVAILABLE:
            raise ImportError("sentence-transformers not installed.")
        print("  Loading embedding model...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_text(text: str) -> np.ndarray:
    model = get_model()
    return model.encode(text, convert_to_numpy=True)


def embed_cv(cv_text: str) -> np.ndarray:
    embedding = embed_text(cv_text[:3000])  # cap to avoid memory issues
    np.save(EMBEDDING_PATH, embedding)
    return embedding


def load_cv_embedding() -> np.ndarray:
    if EMBEDDING_PATH.exists():
        return np.load(EMBEDDING_PATH)
    raise FileNotFoundError("CV embedding not found. Run parse_cv() first.")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))
