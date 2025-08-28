import os
from ingest import Ingestor
from forms.extract_characteristics import extract_characteristics_from_docs
from forms.merge_measurements import merge_cmm_with_characteristics


def test_merge_and_pass_fail(tmp_path):
    # Prepare drawing text
    drawing = tmp_path / "drawing.txt"
    fixture = os.path.join("fixtures", "sample_drawing_text.txt")
    drawing.write_text(open(fixture, "r", encoding="utf-8").read(), encoding="utf-8")

    # Prepare CMM CSV
    cmm_src = os.path.join("fixtures", "cmm_results.csv")
    cmm_path = tmp_path / "cmm_results.csv"
    cmm_path.write_text(open(cmm_src, "r", encoding="utf-8").read(), encoding="utf-8")

    ing = Ingestor()
    info = ing.ingest_file(str(drawing))
    di = ing.doc_store.docs[info["doc_id"]]
    chars = extract_characteristics_from_docs(ing.doc_store, [di])

    measurements = merge_cmm_with_characteristics(chars, [str(cmm_path)])
    assert len(measurements) >= 10
    # Ensure pass/fail computed for at least some rows
    pf_vals = [m.pass_fail for m in measurements]
    assert any(v is True for v in pf_vals) or any(v is False for v in pf_vals)

