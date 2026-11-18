import pandas as pd
from spend_pipeline.classifier import TaxonomyClassifier

def test_zero_shot_returns_runtime_path():
    paths=[("Direct Materials","Aluminium","Can Body Stock"),("Indirect","IT","Software")]
    c=TaxonomyClassifier(paths)
    p=c.predict_zero_shot(["aluminium can body coil material"])
    assert p.paths[0] in paths
    assert 0 <= p.confidence[0] <= 1
