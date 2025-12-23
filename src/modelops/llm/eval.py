from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EvalResult:
    exact_match: float
    precision: float
    recall: float
    f1: float


def evaluate_qa(prediction: str, reference: str) -> EvalResult:
    """Compute exact match and token F1 for QA outputs."""
    pred_tokens = _normalize(prediction)
    ref_tokens = _normalize(reference)

    exact = 1.0 if pred_tokens == ref_tokens else 0.0

    if not pred_tokens or not ref_tokens:
        return EvalResult(exact_match=exact, precision=0.0, recall=0.0, f1=0.0)

    common = set(pred_tokens) & set(ref_tokens)
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return EvalResult(exact_match=exact, precision=precision, recall=recall, f1=f1)


def _normalize(text: str) -> list[str]:
    return [token for token in text.lower().split() if token.strip()]
