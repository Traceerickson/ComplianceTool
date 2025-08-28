import logging
import os
from typing import List, Tuple

from utils.chunking import chunk_text
from utils.embedding import embed_text, EMBED_DIM
from utils.hashing import hash_text
from vector_store import VectorStore

logging.basicConfig(level=logging.INFO)


def parse_pdf(path: str) -> List[Tuple[int, str]]:
    pages: List[Tuple[int, str]] = []
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
        for page_number, layout in enumerate(extract_pages(path), start=1):
            text = ""
            for element in layout:
                if isinstance(element, LTTextContainer):
                    text += element.get_text()
            pages.append((page_number, text))
    except Exception:
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8', errors='ignore')
        pages = [(1, text)]
    return pages


def parse_docx(path: str) -> List[Tuple[int, str]]:
    try:
        import docx  # type: ignore
        document = docx.Document(path)
        text = "\n".join(p.text for p in document.paragraphs)
    except Exception:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(path) as z:
            xml_content = z.read('word/document.xml')
        tree = ET.fromstring(xml_content)
        texts = [node.text for node in tree.iter() if node.text]
        text = "\n".join(texts)
    return [(1, text)]


def parse_txt(path: str) -> List[Tuple[int, str]]:
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    return [(1, text)]


def ingest_documents(data_dir: str, store_path: str) -> None:
    store = VectorStore(EMBED_DIM)
    doc_id = 0
    for root, _, files in os.walk(data_dir):
        for filename in files:
            full_path = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.pdf':
                pages = parse_pdf(full_path)
            elif ext == '.docx':
                pages = parse_docx(full_path)
            elif ext == '.txt':
                pages = parse_txt(full_path)
            else:
                continue
            for page_number, page_text in pages:
                for chunk, line_start, line_end in chunk_text(page_text):
                    embedding = embed_text(chunk)
                    metadata = {
                        'doc_id': str(doc_id),
                        'filename': filename,
                        'page_number': page_number,
                        'text': chunk,
                        'hash': hash_text(chunk),
                        'line_start': line_start,
                        'line_end': line_end,
                    }
                    store.add(embedding, metadata)
                    logging.info(
                        'Ingested %s page %d lines %d-%d',
                        filename, page_number, line_start, line_end
                    )
            doc_id += 1
    store.save(store_path)
    logging.info('Stored %d vectors', len(store.metadatas))
