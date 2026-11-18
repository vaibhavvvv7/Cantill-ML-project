from spend_pipeline.matching import extract_po, extract_po_line

def test_po_normalization():
    assert extract_po("PO 4510109330")=="4510109330"
    assert extract_po("4510085877/10.0")=="4510085877"
    assert extract_po_line("4510085877/10.0")=="10"
