import os
from impact.infer import build_brief, export_brief_docx
from ingest import Ingestor


def test_build_and_export_brief(tmp_path):
    # Prepare documents
    (tmp_path/"SOP-321.txt").write_text("Clause §5.2.3 applies. Material 7075.", encoding="utf-8")
    ing = Ingestor()
    ing.ingest_file(str(tmp_path/"SOP-321.txt"))

    brief = build_brief(eco_text="Update §5.2.3 to ±0.0015 for P-12345 material 7075-T6", max_items=10)
    assert brief.id and len(brief.items) >= 1
    out = export_brief_docx(brief, out_dir=str(tmp_path))
    assert os.path.exists(out)

