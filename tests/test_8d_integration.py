import json
import os

from forms.autofill import generate_8d
from lessons.search import ingest_lessons


def test_8d_integration_with_lessons(tmp_path):
    # Create minimal lessons data
    ncr_dir = os.path.join('data','ncr')
    capa_dir = os.path.join('data','capa')
    os.makedirs(ncr_dir, exist_ok=True)
    os.makedirs(capa_dir, exist_ok=True)

    with open(os.path.join(ncr_dir, 'NCR-L1.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'id': 'NCR-L1',
            'part_number': 'P-1',
            'defect': 'Porosity in weld',
            'description': 'Porosity due to gas',
            'owner': 'QA',
            'outcome': 'Fixed',
            'cycle_time': 3,
            'evidence_refs': []
        }, f)
    with open(os.path.join(capa_dir, 'CAPA-L1.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'id': 'CAPA-L1', 'ncr_id': 'NCR-L1',
            'root_cause': 'Insufficient gas flow',
            'corrective_action': 'Increase gas flow',
            'containment': 'Hold', 'verification': 'Reinspect', 'owner': 'QE', 'completed_at': '2025-01-01'
        }, f)

    ingest_lessons(ncr_dir=ncr_dir, capa_dir=capa_dir)

    bundle = generate_8d(ncr_json={'symptom':'porosity'}, evidence_doc_ids=[], lessons_query='porosity weld')
    assert bundle.eightd
    assert (bundle.eightd.D4_root_cause or '').lower().find('gas') >= 0
    assert (bundle.eightd.D5_corrective_action or '').lower().find('increase') >= 0

