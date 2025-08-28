from impact.infer import build_brief
from ingest import Ingestor


def test_impact_inference_on_synthetic(tmp_path):
    # Create a few assets
    (tmp_path/"SOP-200.txt").write_text("Material 7075 and clause §5.2.3 apply to P-12345.", encoding="utf-8")
    (tmp_path/"CHECKLIST_A.txt").write_text("Verify per §5.2.3.", encoding="utf-8")
    (tmp_path/"NCP-77.txt").write_text("Offsets for P-12345.", encoding="utf-8")
    ing = Ingestor()
    for f in tmp_path.iterdir():
        ing.ingest_file(str(f))

    eco = "Change §5.2.3 tolerance ±0.0015 and material 7075-T6 for P-12345"
    brief = build_brief(eco_text=eco, max_items=20)
    assert len(brief.items) >= 3
    assert any(it.impact_score >= 40 for it in brief.items)

