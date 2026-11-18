import pandas as pd
from spend_pipeline.ingest import apply_fx

def test_inline_fx_divides_units_per_usd():
    cfg={"reporting_currency":"USD","fx":{"inline_rate_column":"currency_rate"}}
    df=pd.DataFrame({"currency":["EUR","USD"],"amount_net":[200.0,50.0],"currency_rate":[2.0,None],"date":pd.to_datetime(["2024-01-01","2024-01-01"])})
    out=apply_fx(cfg,df,{})
    assert out.amount_reporting.tolist()==[100.0,50.0]
