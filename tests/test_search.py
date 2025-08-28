from ingest import ingest_documents
from search import load_search_engine


def test_search_returns_citations(tmp_path):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'a.txt').write_text('Regulations require compliance procedures', encoding='utf-8')
    store_path = tmp_path / 'store'
    ingest_documents(str(data_dir), str(store_path))

    engine = load_search_engine(str(store_path))
    results = engine.search('compliance procedures', top_n=1)
    assert results
    citation = results[0]['citation']
    assert citation['filename'] == 'a.txt'
    assert citation['page_number'] == 1
    assert citation['lines'][0] <= citation['lines'][1]
