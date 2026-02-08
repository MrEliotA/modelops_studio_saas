from __future__ import annotations
import re
import hashlib
from dataclasses import dataclass

def normalize_text(text: str) -> str:
    # basic cleaning: collapse whitespace
    return re.sub(r"\s+", " ", text).strip()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

@dataclass
class Chunk:
    chunk_no: int
    start: int
    end: int
    text: str

def fixed_chunk(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >=0 and < chunk_size")

    chunks: list[Chunk] = []
    n = len(text)
    start = 0
    idx = 0
    while start < n:
        end = min(start + chunk_size, n)
        # try to break on whitespace for better coherence
        if end < n:
            ws = text.rfind(" ", start, end)
            if ws > start + int(chunk_size * 0.6):
                end = ws
        chunk_txt = text[start:end].strip()
        if chunk_txt:
            chunks.append(Chunk(chunk_no=idx, start=start, end=end, text=chunk_txt))
            idx += 1
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks
