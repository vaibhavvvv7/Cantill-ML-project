# Blind-Test Runbook

The build code must remain frozen after 10:00 AM. Only configs and required output files should be added during the blind test.

## Before 10:00 AM

```bash
pytest -q
python -m spend_pipeline --config configs/company_a.yaml --output outputs/vaibhav__A.csv
python -m spend_pipeline --config configs/company_b.yaml --output outputs/vaibhav__B.csv
```

Confirm confidential datasets are not tracked:

```bash
git status
git ls-files | grep -E 'company_[ABC]/.*\.csv|Cantill_DataML_Task_Kit' && echo "CHECK DATA LEAK"
```

## 10:00 AM - receive A2, B2, C

### A2

A2 uses the A layout. Point the existing A config at the new file(s), either by placing them at the configured paths in a temporary data root or by making a blind-test copy of the config if filenames differ. Do not modify Python.

Write:

```text
submission/vaibhav__A2.csv
```

### B2

Same procedure using the B config and new B2 file.

Write:

```text
submission/vaibhav__B2.csv
```

### C

1. Copy `configs/company_c_template.yaml` to `configs/company_c.yaml`.
2. Inspect C headers and taxonomy headers only as needed to map fields.
3. Set the C taxonomy level columns (1-4).
4. Map amount, currency, dates, supplier/vendor, material/item, status and description fields.
5. Configure gross/net semantics and FX only if C needs them.
6. Run unchanged Python.

```bash
python -m spend_pipeline \
  --config configs/company_c.yaml \
  --output submission/vaibhav__C.csv \
  --diagnostics submission/C_diagnostics.json
```

## Validation

```bash
python scripts/validate_submission.py submission/vaibhav__A2.csv
python scripts/validate_submission.py submission/vaibhav__B2.csv
python scripts/validate_submission.py submission/vaibhav__C.csv
```

Check diagnostics for:

- input/output row equality;
- unexpected all-zero or all-one include rates;
- missing FX;
- parse failures;
- implausible supplier/item cluster counts;
- total spend;
- confidence distribution.

## Final Git action

Push only:

- `configs/company_c.yaml`
- `submission/vaibhav__A2.csv`
- `submission/vaibhav__B2.csv`
- `submission/vaibhav__C.csv`

Do not change Python after the build deadline.
