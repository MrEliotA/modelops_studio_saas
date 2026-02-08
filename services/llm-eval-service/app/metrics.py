from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return float(num) / float(den)


def classification_accuracy(y_pred: list[Any], y_true: list[Any]) -> float:
    if len(y_pred) != len(y_true) or not y_true:
        return 0.0
    correct = sum(1 for p, t in zip(y_pred, y_true) if p == t)
    return _safe_div(correct, len(y_true))


def classification_macro_f1(y_pred: list[Any], y_true: list[Any]) -> float:
    if len(y_pred) != len(y_true) or not y_true:
        return 0.0

    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0

    f1s: list[float] = []
    for lbl in labels:
        tp = sum(1 for p, t in zip(y_pred, y_true) if p == lbl and t == lbl)
        fp = sum(1 for p, t in zip(y_pred, y_true) if p == lbl and t != lbl)
        fn = sum(1 for p, t in zip(y_pred, y_true) if p != lbl and t == lbl)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)

    return float(sum(f1s) / len(f1s))


def regression_mae(y_pred: list[float], y_true: list[float]) -> float:
    if len(y_pred) != len(y_true) or not y_true:
        return 0.0
    err = [abs(float(p) - float(t)) for p, t in zip(y_pred, y_true)]
    return float(sum(err) / len(err))


def regression_mse(y_pred: list[float], y_true: list[float]) -> float:
    if len(y_pred) != len(y_true) or not y_true:
        return 0.0
    err = [(float(p) - float(t)) ** 2 for p, t in zip(y_pred, y_true)]
    return float(sum(err) / len(err))


def exact_match_rate(y_pred: list[str], y_true: list[str]) -> float:
    if len(y_pred) != len(y_true) or not y_true:
        return 0.0
    correct = sum(1 for p, t in zip(y_pred, y_true) if str(p).strip() == str(t).strip())
    return _safe_div(correct, len(y_true))


def retrieval_recall_at_k(
    ranked_lists: list[list[Any]], relevant_lists: list[list[Any]], k: int
) -> float:
    if len(ranked_lists) != len(relevant_lists) or not relevant_lists:
        return 0.0
    k = max(1, int(k))
    hits = 0
    for ranked, rel in zip(ranked_lists, relevant_lists):
        rset = set(rel or [])
        topk = ranked[:k] if isinstance(ranked, list) else []
        if rset and any(x in rset for x in topk):
            hits += 1
    return _safe_div(hits, len(relevant_lists))


def retrieval_mrr_at_k(
    ranked_lists: list[list[Any]], relevant_lists: list[list[Any]], k: int
) -> float:
    if len(ranked_lists) != len(relevant_lists) or not relevant_lists:
        return 0.0
    k = max(1, int(k))
    rr_sum = 0.0
    for ranked, rel in zip(ranked_lists, relevant_lists):
        rset = set(rel or [])
        topk = ranked[:k] if isinstance(ranked, list) else []
        rr = 0.0
        for i, item in enumerate(topk):
            if item in rset:
                rr = 1.0 / float(i + 1)
                break
        rr_sum += rr
    return float(rr_sum / len(relevant_lists))
