import os
from ingest import Ingestor
from impact.graph import build_graph, load_graph


def test_graph_edges_from_refs(tmp_path):
    # Create a simple TXT with refs
    p = tmp_path / "SOP-123.txt"
    p.write_text("See §5.2.3 and Program NCP-09-334. Fixture FX-22 required.", encoding="utf-8")
    ing = Ingestor()
    ing.ingest_file(str(p))

    g = build_graph(ing.doc_store, out_path=os.path.join("data", "graph.json"))
    nodes = {n['id']: n for n in g['nodes']}
    edges = g['edges']
    assert any(e['type']=='references' for e in edges)
    assert any('clause:' in e['dst'] for e in edges)

