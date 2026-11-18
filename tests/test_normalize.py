from spend_pipeline.normalize import parse_number, parse_vat

def test_numbers():
    assert parse_number("5,266.63")==5266.63
    assert parse_number("(100.50)")==-100.5

def test_vat():
    assert parse_vat("15")==0.15
    assert parse_vat("15%")==0.15
    assert parse_vat("0.15")==0.15
    assert parse_vat(None)==0.15
