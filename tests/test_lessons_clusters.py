import os
import json

from lessons.search import ingest_lessons
from lessons.cluster_lessons import compute_clusters


def test_lessons_clusters(tmp_path):
    ncr_dir = os.path.join('data','ncr')
    capa_dir = os.path.join('data','capa')
    os.makedirs(ncr_dir, exist_ok=True)
    os.makedirs(capa_dir, exist_ok=True)

    # minimal NCR dataset
    for i in range(3):
        with open(os.path.join(ncr_dir, f"NCR-T{i}.json"), 'w', encoding='utf-8') as f:
            f.write(json.dumps({
                'id': f'NCR-T{i}',
                'part_number': 'P-11111',
                'defect': 'Porosity in weld' if i<2 else 'Crack in weld',
                'description': '7075-T6' if i<2 else '6061-T6',
                'owner': 'QA',
                'outcome': 'Adjusted process',
                'cycle_time': 5,
                'evidence_refs': []
            }))

    ingest_lessons(ncr_dir=ncr_dir, capa_dir=capa_dir)
    data = compute_clusters(num_clusters=2)
    assert 'clusters' in data and len(data['clusters']) >= 1
    # Look for keyword presence
    kw = ','.join(','.join(c.get('keywords', [])) for c in data['clusters'])
    assert 'porosity' in kw or 'weld' in kw

