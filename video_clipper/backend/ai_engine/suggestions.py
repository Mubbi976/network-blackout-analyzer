import threading
from typing import Any

from backend.config import get_settings

_CATEGORIES = [
    ("educational explanation", "A clear educational explanation that teaches a useful concept."),
    ("surprising insight", "A surprising discovery, unexpected fact, or revelation."),
    ("strong opinion", "A strong, memorable opinion or persuasive argument."),
    ("question and answer", "An engaging question followed by a useful answer."),
    ("storytelling", "A vivid personal story with a compelling narrative."),
    ("humor", "A funny or amusing moment that could entertain viewers."),
]
_MODEL_LOCK = threading.Lock()
_SEMANTIC_MODEL: Any = None


def _model() -> Any:
    global _SEMANTIC_MODEL

    if _SEMANTIC_MODEL is not None:
        return _SEMANTIC_MODEL
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    with _MODEL_LOCK:
        if _SEMANTIC_MODEL is None:
            _SEMANTIC_MODEL = SentenceTransformer(
                settings.semantic_model,
                device="cpu",
                cache_folder=str(settings.model_cache_dir),
            )
        return _SEMANTIC_MODEL


def _overlap_ratio(left: tuple[float, float], right: tuple[float, float]) -> float:
    intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
    union = max(left[1], right[1]) - min(left[0], right[0])
    return intersection / union if union else 0


def suggest_candidates(
    transcript: dict[str, Any],
    max_candidates: int = 8,
    target_seconds: int = 30,
) -> list[dict[str, Any]]:
    segments = transcript.get("segments", [])
    if not segments:
        return []
    model = _model()
    texts = [segment["text"] for segment in segments]
    embeddings = model.encode(
        texts + [description for _, description in _CATEGORIES],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    sentence_vectors = embeddings[: len(texts)]
    category_vectors = embeddings[len(texts) :]
    similarities = sentence_vectors @ category_vectors.T

    ranked = []
    for index, segment in enumerate(segments):
        category_index = int(similarities[index].argmax())
        semantic_score = float(similarities[index][category_index])
        text = segment["text"]
        punctuation_bonus = 0.08 if text.rstrip().endswith(("!", "?")) else 0
        length_bonus = min(len(text.split()) / 24, 1) * 0.08
        ranked.append(
            (
                semantic_score + punctuation_bonus + length_bonus,
                index,
                category_index,
            )
        )

    ranked.sort(reverse=True)
    candidates = []
    seen: list[tuple[float, float]] = []
    for raw_score, anchor, category_index in ranked:
        target = max(15, target_seconds)
        left = right = anchor
        while right + 1 < len(segments) and (
            segments[right]["end"] - segments[left]["start"] < target
        ):
            if left > 0 and (
                segments[anchor]["start"] - segments[left - 1]["start"]
                < segments[right + 1]["end"] - segments[anchor]["end"]
            ):
                left -= 1
            else:
                right += 1
        start = float(segments[left]["start"])
        end = float(segments[right]["end"])
        if end - start < 8 or any(_overlap_ratio((start, end), interval) > 0.65 for interval in seen):
            continue
        excerpt = " ".join(segment["text"] for segment in segments[left : right + 1]).strip()
        anchor_text = segments[anchor]["text"].strip()
        title = anchor_text[:76].rstrip(" ,.!?") or _CATEGORIES[category_index][0].title()
        candidates.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "focus_time": round(
                    (float(segments[anchor]["start"]) + float(segments[anchor]["end"])) / 2,
                    3,
                ),
                "title": title,
                "excerpt": excerpt,
                "reason": f"Semantically relevant to {_CATEGORIES[category_index][0]}",
                "confidence": round(max(0, min(1, raw_score / 1.25)), 3),
                "category": _CATEGORIES[category_index][0],
            }
        )
        seen.append((start, end))
        if len(candidates) >= max_candidates:
            break
    return candidates
