import json
import os

from lessons.search import ingest_lessons, search_lessons


def test_lessons_search(tmp_path):
    ncr_dir = os.path.join('data','ncr')
    capa_dir = os.path.join('data','capa')
    os.makedirs(ncr_dir, exist_ok=True)
    os.makedirs(capa_dir, exist_ok=True)

    # Create a few NCRs with porosity keyword
    ncrs = [
        {
            "id": "NCR-1001",
            "part_number": "P-12345",
            "defect": "Porosity in 7075-T6 weld",
            "description": "Observed porosity clusters near joint.",
            "date": "2025-08-01",
            "owner": "A. Eng",
            "outcome": "Corrected with purge and preheat",
            "cycle_time": 12,
            "evidence_refs": [
                {"doc_id": None, "filename":"weld_spec.pdf", "page":1, "line":5}
            ]
        },
        {
            "id": "NCR-1002",
            "part_number": "P-99999",
            "defect": "Porosity in casting",
            "description": "Porosity exceeding limit per spec.",
            "date": "2025-08-05",
            "owner": "B. Eng",
            "outcome": "Impregnation applied",
            "cycle_time": 8,
            "evidence_refs": []
        }
    ]
    for r in ncrs:
        with open(os.path.join(ncr_dir, f"{r['id']}.json"), 'w', encoding='utf-8') as f:
            json.dump(r, f)

    capa = {
        "id": "CAPA-2001",
        "ncr_id": "NCR-1001",
        "root_cause": "Inadequate shielding gas flow",
        "corrective_action": "Increase gas flow and preheat per WPS",
        "containment": "Hold affected parts",
        "verification": "NDT re-inspection",
        "owner": "C. QE",
        "completed_at": "2025-08-20"
    }
    with open(os.path.join(capa_dir, f"{capa['id']}.json"), 'w', encoding='utf-8') as f:
        json.dump(capa, f)

    ingest_lessons(ncr_dir=ncr_dir, capa_dir=capa_dir)
    res = search_lessons("porosity 7075-T6", top_k=5)
    assert len(res) >= 1
    # Result contains corrective action and citations
    r0 = res[0]
    assert 'corrective_action' in r0
    assert isinstance(r0.get('citations'), list) and len(r0['citations']) >= 1

