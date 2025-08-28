import os
from ingest import Ingestor
from forms.extract_characteristics import extract_characteristics_from_docs


def test_extract_characteristics_from_text(tmp_path):
    # Create a simple TXT drawing using fixture
    drawing = tmp_path / "drawing.txt"
    fixture = os.path.join("fixtures", "sample_drawing_text.txt")
    drawing.write_text(open(fixture, "r", encoding="utf-8").read(), encoding="utf-8")

    ing = Ingestor()
    info = ing.ingest_file(str(drawing))
    di = ing.doc_store.docs[info["doc_id"]]

    chars = extract_characteristics_from_docs(ing.doc_store, [di])
    assert len(chars) >= 10
    # Each has id, description, citation
    assert all(c.char_id and c.description and c.citation for c in chars)

