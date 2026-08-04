"""
Text chunker — splits document text into overlapping chunks for embedding.

Strategy:
  1. Structural pre-split: detect common section-boundary patterns (headings,
     all-caps labels, multi-blank-line gaps) and split there first.
  2. Each structural segment is then chunked with a token sliding window,
     but NEVER split across a structural boundary unless a single segment
     exceeds 2×CHUNK_SIZE tokens.
  3. Overlap between chunks is 100 tokens (up from 50) so semantic context
     bleeds across boundaries, reducing the risk of a query matching mid-chunk.

Uses tiktoken for accurate token counting.
"""
import re
from typing import List, Dict

import tiktoken

# Target tokens per chunk and overlap
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100          # increased from 50 → 100
MAX_SINGLE_SEGMENT = CHUNK_SIZE * 2  # segments larger than this are sub-chunked

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


# ── Structural boundary detection ─────────────────────────────────────────────

# Patterns that signal a new document section:
_SECTION_PATTERNS = [
    # Markdown headings: # Heading, ## Subheading
    re.compile(r"(?m)^#{1,3}\s+\S"),
    # ALL CAPS lines (≥3 chars) used as headings in PDFs/resumes
    re.compile(r"(?m)^[A-Z][A-Z &\-/]{2,}:?\s*$"),
    # Title Case lines ending with colon (common in resumes: "Work Experience:")
    re.compile(r"(?m)^[A-Z][a-zA-Z\s&\-/]{2,}:\s*$"),
    # Two or more consecutive blank lines
    re.compile(r"\n{3,}"),
]


def _split_on_structure(text: str) -> List[str]:
    """
    Split text into structural segments by detecting section boundaries.
    Returns a list of non-empty text segments.
    """
    # Build a unified set of split positions
    split_positions = set([0, len(text)])

    for pattern in _SECTION_PATTERNS:
        for match in pattern.finditer(text):
            split_positions.add(match.start())

    positions = sorted(split_positions)

    segments = []
    for i in range(len(positions) - 1):
        seg = text[positions[i]:positions[i + 1]].strip()
        if seg:
            segments.append(seg)

    return segments if segments else [text.strip()]


# ── Token-window chunking of a single segment ─────────────────────────────────

def _chunk_segment(text: str, start_index: int) -> List[Dict]:
    """
    Apply sliding-window token chunking to a single text segment.
    Returns chunks with chunk_index starting at start_index.
    """
    enc = _get_encoder()
    tokens = enc.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        return []

    chunks = []
    chunk_index = start_index
    pos = 0

    while pos < total_tokens:
        end = min(pos + CHUNK_SIZE, total_tokens)
        chunk_tokens = tokens[pos:end]
        chunk_str = enc.decode(chunk_tokens).strip()

        if chunk_str:
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_str,
                "token_count": len(chunk_tokens),
            })
            chunk_index += 1

        if end >= total_tokens:
            break

        pos = end - CHUNK_OVERLAP

    return chunks


# ── Public interface ──────────────────────────────────────────────────────────

def chunk_text(text: str) -> List[Dict]:
    """
    Split text into overlapping chunks that respect document structure.

    For short texts (≤ CHUNK_SIZE tokens) returns a single chunk.
    For longer texts:
      1. Splits on structural boundaries (headings, blank lines, etc.)
      2. Combines consecutive segments that are too small to chunk alone
      3. Applies token-window chunking within each segment

    Returns list of {chunk_index, text, token_count}.
    """
    if not text or not text.strip():
        return []

    enc = _get_encoder()
    total_tokens = len(enc.encode(text))

    # Very short document: single chunk, no splitting needed
    if total_tokens <= CHUNK_SIZE:
        return [{
            "chunk_index": 0,
            "text": text.strip(),
            "token_count": total_tokens,
        }]

    # Split on structural boundaries
    segments = _split_on_structure(text)

    # Merge tiny adjacent segments (< 50 tokens) into the next one
    # so we don't create useless micro-chunks
    merged_segments: List[str] = []
    buffer = ""
    for seg in segments:
        seg_tokens = len(enc.encode(seg))
        if seg_tokens < 50 and buffer:
            buffer += "\n\n" + seg
        elif buffer:
            merged_segments.append(buffer)
            buffer = seg
        else:
            buffer = seg
    if buffer:
        merged_segments.append(buffer)

    # Chunk each merged segment
    all_chunks: List[Dict] = []
    chunk_counter = 0
    for seg in merged_segments:
        seg_tokens = len(enc.encode(seg))
        if seg_tokens <= MAX_SINGLE_SEGMENT:
            # Small enough: emit as one chunk (no sub-splitting)
            seg_str = seg.strip()
            if seg_str:
                all_chunks.append({
                    "chunk_index": chunk_counter,
                    "text": seg_str,
                    "token_count": seg_tokens,
                })
                chunk_counter += 1
        else:
            # Large segment: apply sliding window within the segment
            sub_chunks = _chunk_segment(seg, chunk_counter)
            all_chunks.extend(sub_chunks)
            chunk_counter += len(sub_chunks)

    return all_chunks
