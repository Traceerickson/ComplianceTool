import os
from forms.autofill import generate_as9102
from forms.exporter import export_draft
from ingest import Ingestor


def test_exporter_creates_files(tmp_path):
    # Setup drawing and cmm
    drawing = tmp_path / "drawing.txt"
    drawing.write_text(open(os.path.join("fixtures","sample_drawing_text.txt"),"r",encoding="utf-8").read(), encoding="utf-8")
    cmm_path = tmp_path / "cmm_results.csv"
    cmm_path.write_text(open(os.path.join("fixtures","cmm_results.csv"),"r",encoding="utf-8").read(), encoding="utf-8")

    ing = Ingestor()
    info = ing.ingest_file(str(drawing))
    bundle = generate_as9102([info["doc_id"]], [str(cmm_path)], ["1","2","3"]) 

    out_dir = tmp_path / "exports"
    outs = export_draft(bundle, out_dir=str(out_dir), fmt="all")
    assert any(p.endswith('.docx') for p in outs)
    assert any(p.endswith('.xlsx') for p in outs)
    # Check evidence JSON exists
    assert (out_dir / f"draft_{bundle.draft_id}.json").exists()

