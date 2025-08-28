import json
import os

from services.audit_pack import build_audit_pack
from ingest import Ingestor


def test_build_audit_pack_query(tmp_path):
    # Create a sample text drawing and ingest
    drawing = tmp_path / "drawing.txt"
    drawing.write_text(open(os.path.join("fixtures","sample_drawing_text.txt"),"r",encoding="utf-8").read(), encoding="utf-8")
    ing = Ingestor()
    info = ing.ingest_file(str(drawing))

    # Build a small pack
    res = build_audit_pack(query="Bracket", max_items=5, filters={"doc_ids": [info["doc_id"]]}, redaction={"mode":"overlay","patterns":["P-\\d+"]})
    assert res.get("pack_id")
    # Verify index.html, manifest.json and zip exist
    assert os.path.exists(res["index_path"]) and os.path.exists(res["manifest_path"]) and os.path.exists(res["zip_path"]) 

    # Check hashes.json and chain_of_custody.json inside pack dir
    pack_dir = os.path.join("packs", res["pack_id"])
    hashes = json.load(open(os.path.join(pack_dir, "hashes.json"),"r",encoding="utf-8"))
    assert isinstance(hashes, dict) and len(hashes) >= 1
    coc = json.load(open(os.path.join(pack_dir, "chain_of_custody.json"),"r",encoding="utf-8"))
    assert coc.get("pack_id") == res["pack_id"]

