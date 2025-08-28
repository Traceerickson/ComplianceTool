import os
from ingest import Ingestor
from forms.autofill import generate_as9102


def test_generate_as9102_draft(tmp_path):
    # Drawing
    drawing = tmp_path / "drawing.txt"
    fixture = os.path.join("fixtures", "sample_drawing_text.txt")
    drawing.write_text(open(fixture, "r", encoding="utf-8").read(), encoding="utf-8")

    # CMM
    cmm_src = os.path.join("fixtures", "cmm_results.csv")
    cmm_path = tmp_path / "cmm_results.csv"
    cmm_path.write_text(open(cmm_src, "r", encoding="utf-8").read(), encoding="utf-8")

    ing = Ingestor()
    info = ing.ingest_file(str(drawing))
    doc_id = info["doc_id"]

    bundle = generate_as9102(doc_ids=[doc_id], cmm_files=[str(cmm_path)], form_levels=["1","2","3"]) 
    assert bundle.completion_score >= 70
    assert bundle.form2 and len(bundle.form2.characteristics) >= 10
    assert bundle.form3 and len(bundle.form3.measurements) >= 10
    # Every top-level field present should have provenance
    assert any(k.startswith("form1.") for k in bundle.provenance)

