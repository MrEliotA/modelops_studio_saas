from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Rule:
    name: str
    label: str
    keywords: list[str]
    is_active: bool = True


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def score_text(text: str, keywords: list[str]) -> int:
    txt = _normalize(text)
    if not txt:
        return 0
    score = 0
    for kw in keywords:
        k = _normalize(str(kw))
        if not k:
            continue
        if k in txt:
            score += 1
    return score


def apply_rules(text: str, rules: list[Rule], top_n: int = 3) -> dict[str, Any]:
    scored = []
    for r in rules:
        if not r.is_active:
            continue
        s = score_text(text, r.keywords)
        if s > 0:
            scored.append((r.label, r.name, s))
    scored.sort(key=lambda x: x[2], reverse=True)

    labels = [x[0] for x in scored[:top_n]]
    best = labels[0] if labels else None
    return {"best_label": best, "labels": labels, "matches": [{"label": l, "rule": n, "score": s} for l, n, s in scored[:top_n]]}
