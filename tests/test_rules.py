import pandas as pd
from spend_pipeline.spend_rules import SpendRuleEngine

def test_status_rules():
    cfg={"spend_rules":{"status_column":"status","approved_statuses":["Paid","Approved"],"cancelled_statuses":["Cancelled"]}}
    d=pd.DataFrame({"status":["Paid","Cancelled","On Hold"]})
    inc,r=SpendRuleEngine(cfg).apply(d)
    assert inc.tolist()==[1,0,0]
    assert r.tolist()==["","CANCELLED","NOT_APPROVED"]
