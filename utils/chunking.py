from typing import List, Tuple


def split_into_lines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def count_tokens_approx(text: str) -> int:
    """Approximate token count by splitting on whitespace (sufficient for prototype)."""
    return len(text.split())


def chunk_text(
    text: str,
    max_tokens: int = 500,
    preserve_lines: bool = True,
) -> List[Tuple[str, Tuple[int, int]]]:
    """
    Chunk text into ~max_tokens pieces while preserving line boundaries when possible.

    Returns list of tuples: (chunk_text, (line_start, line_end)) where line_start/end are
    1-based inclusive line numbers relative to the start of `text`.
    """
    if not text:
        return []

    if not preserve_lines:
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunk = " ".join(words[start:end])
            chunks.append((chunk, (1, 1)))
            start = end
        return chunks

    lines = split_into_lines(text)
    chunks = []
    current_lines: List[str] = []
    current_token_count = 0
    chunk_start_line = 1
    for idx, line in enumerate(lines, start=1):
        tokens = line.split()
        prospective = current_token_count + len(tokens)
        if prospective > max_tokens and current_lines:
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                chunks.append((chunk_text, (chunk_start_line, idx - 1)))
            current_lines = [line]
            current_token_count = len(tokens)
            chunk_start_line = idx
        else:
            current_lines.append(line)
            current_token_count = prospective

    if current_lines:
        chunk_text = "\n".join(current_lines).strip()
        if chunk_text:
            chunks.append((chunk_text, (chunk_start_line, len(lines))))

    return chunks

