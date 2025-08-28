from typing import List, Tuple


def chunk_text(text: str, chunk_size: int = 500) -> List[Tuple[str, int, int]]:
    """
    Split text into chunks of approximately `chunk_size` tokens.
    Returns list of tuples: (chunk_text, line_start, line_end).
    """
    lines = text.splitlines()
    chunks: List[Tuple[str, int, int]] = []
    buffer: List[str] = []
    token_count = 0
    start_line = 1
    for i, line in enumerate(lines, start=1):
        tokens = line.split()
        if token_count + len(tokens) > chunk_size and buffer:
            chunk = "\n".join(buffer)
            chunks.append((chunk, start_line, i - 1))
            buffer = []
            token_count = 0
            start_line = i
        buffer.append(line)
        token_count += len(tokens)
    if buffer:
        chunk = "\n".join(buffer)
        chunks.append((chunk, start_line, len(lines)))
    return chunks
