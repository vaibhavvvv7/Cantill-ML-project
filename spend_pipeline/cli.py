from __future__ import annotations
import argparse, json
from .pipeline import run_pipeline

def main():
    ap=argparse.ArgumentParser(description="Config-driven spend normalization and classification pipeline")
    ap.add_argument("--config",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--data-root",default=None)
    ap.add_argument("--no-labels",action="store_true",help="Ignore labels and use taxonomy-only classification")
    ap.add_argument("--diagnostics",default=None)
    args=ap.parse_args()
    _,diag=run_pipeline(args.config,args.output,args.data_root,not args.no_labels,args.diagnostics)
    print(json.dumps(diag,indent=2))
if __name__=="__main__": main()
