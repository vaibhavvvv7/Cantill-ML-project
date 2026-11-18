#!/bin/sh
set -eu
DATA_ROOT="${CANTILL_DATA_ROOT:-data/Cantill_DataML_Task_Kit}"
python -m spend_pipeline --config configs/company_a.yaml --data-root "$DATA_ROOT" --output outputs/vaibhav__A.csv --diagnostics outputs/A_diagnostics.json
python -m spend_pipeline --config configs/company_b.yaml --data-root "$DATA_ROOT" --output outputs/vaibhav__B.csv --diagnostics outputs/B_diagnostics.json
