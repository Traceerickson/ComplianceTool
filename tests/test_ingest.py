import os
import zipfile
from pathlib import Path

from ingest import ingest_documents
from vector_store import VectorStore


def create_docx(path: Path, text: str) -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, 'w') as docx:
        docx.writestr('[Content_Types].xml', (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/></Types>'
        ))
        docx.writestr('_rels/.rels', (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        ))
        docx.writestr('word/_rels/document.xml.rels', (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        ))
        docx.writestr('word/document.xml', xml)


def test_ingest_parses_files(tmp_path):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    # txt
    (data_dir / 'sample.txt').write_text('Hello from txt file', encoding='utf-8')
    # docx
    create_docx(data_dir / 'sample.docx', 'Hello from docx file')
    # pdf (plain text for fallback parser)
    (data_dir / 'sample.pdf').write_text('Hello from pdf file', encoding='utf-8')

    store_path = tmp_path / 'store'
    ingest_documents(str(data_dir), str(store_path))

    store = VectorStore.load(str(store_path))
    filenames = {m['filename'] for m in store.metadatas}
    assert {'sample.txt', 'sample.docx', 'sample.pdf'} <= filenames
    assert len(store.metadatas) > 0
