from impact.eco_parser import parse_eco_text


def test_parse_eco_text_basic():
    txt = "ECO: Update §5.2.3 tolerance to ±0.0015 and change material to 7075-T6 for P-12345."
    eco = parse_eco_text(txt, effective_date="2025-01-01")
    assert '5.2.3' in eco.clauses
    assert '7075-T6'.split('-')[0] in eco.materials[0]
    assert any('0.0015' in d for d in eco.deltas)
    assert 'P-12345' in eco.parts

