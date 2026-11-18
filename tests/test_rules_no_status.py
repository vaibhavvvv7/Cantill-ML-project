import pandas as pd
from spend_pipeline.spend_rules import SpendRuleEngine

def test_no_status_rule_when_not_configured():
    d=pd.DataFrame({"status":["",""]})
    inc,r=SpendRuleEngine({"spend_rules":{}}).apply(d)
    assert inc.tolist()==[1,1]
    assert r.tolist()==["",""]
