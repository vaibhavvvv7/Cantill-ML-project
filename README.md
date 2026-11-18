# Cantill Spend Pipeline

A config-driven procurement spend pipeline for the Cantill.ai Data & ML task.

It ingests heterogeneous purchasing systems, normalizes amounts/dates/currency, applies spend exclusions, de-duplicates cross-system records, resolves supplier/item identities, classifies included spend into a taxonomy loaded at run time, and writes the exact required submission schema.

## Key design constraints

- **New company = new YAML config, not new Python code.**
- Taxonomy names are read from CSV at run time; no A/B category names are embedded in the classifier.
- Company A's ERP is the primary source when an invoice-tool row matches it.
- Company B converts to USD using inline rates first, then monthly FX fallback.
- Labels are optional. If absent, the classifier automatically falls back to taxonomy-only classification.
- Confidential task CSVs are ignored by Git and are never copied into the repository.

## Repository layout

```text
configs/
  company_a.yaml
  company_b.yaml
  company_c_template.yaml
spend_pipeline/
  cli.py
  config.py
  ingest.py
  normalize.py
  spend_rules.py
  matching.py
  entities.py
  taxonomy.py
  classifier.py
  pipeline.py
  evaluate.py
scripts/
  run_all.sh
  evaluate_outputs.py
  validate_submission.py
tests/
outputs/
submission/
APPROACH.md
DECISIONS.md
BLIND_TEST.md
```

## Setup

Python 3.10+ is recommended.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Place the supplied kit outside Git-tracked files, for example:

```text
data/
  Cantill_DataML_Task_Kit/
    company_A/
    company_B/
    output_template.csv
```

The `data/` directory is ignored by `.gitignore`.

Alternatively, point directly to the extracted task-kit directory with `--data-root` or the `CANTILL_DATA_ROOT` environment variable.

## One-command runs

Company A:

```bash
python -m spend_pipeline \
  --config configs/company_a.yaml \
  --output outputs/vaibhav__A.csv
```

Company B:

```bash
python -m spend_pipeline \
  --config configs/company_b.yaml \
  --output outputs/vaibhav__B.csv
```

If the kit is elsewhere:

```bash
python -m spend_pipeline \
  --config configs/company_a.yaml \
  --data-root /path/to/Cantill_DataML_Task_Kit \
  --output outputs/vaibhav__A.csv
```

Run both:

```bash
./scripts/run_all.sh
```

## Zero-label mode

Labels are not required. To force taxonomy-only classification:

```bash
python -m spend_pipeline \
  --config configs/company_a.yaml \
  --output /tmp/A_zero_label.csv \
  --no-labels
```

Measure the required A labels-hidden experiment:

```bash
python -m spend_pipeline.evaluate \
  --config configs/company_a.yaml
```

## Company C / blind test

Copy the template:

```bash
cp configs/company_c_template.yaml configs/company_c.yaml
```

Edit only:

- input filename;
- taxonomy filename and level column names;
- raw-to-canonical column mappings;
- amount semantics;
- date columns;
- status rules, if present;
- description/feature columns.

Then run the unchanged code:

```bash
python -m spend_pipeline \
  --config configs/company_c.yaml \
  --output submission/vaibhav__C.csv
```

See `BLIND_TEST.md` for the timed procedure.

## Output schema

Every input record is retained, including excluded rows:

```text
record_id
include
exclusion_reason
supplier_key
item_key
spend
l1
l2
l3
l4
confidence
```

The pipeline validates before writing that:

- row count equals input count;
- `record_id` is unique;
- excluded spend is zero;
- exclusion codes are valid;
- included rows have blank exclusion reason;
- confidence is between 0 and 1;
- every emitted category path exists in the runtime taxonomy.

## Tests

```bash
pytest -q
```

The tests cover amount/VAT normalization, PO normalization, status/exclusion logic, taxonomy-only classification, and FX behavior.

## Current build outputs

The repository includes generated A/B outputs and compact diagnostics only. It does **not** contain the confidential source datasets.

Observed build-run row counts:

- A: 65,549 rows (37,029 ERP + 28,520 tool)
- B: 41,028 rows

See `outputs/A_diagnostics.json` and `outputs/B_diagnostics.json` for run summaries.

## Notes

The implementation is intentionally local and key-free. No paid API is required, so API cost is **$0 per 1,000 lines**. The taxonomy-only fallback is lexical and deterministic; its measured labels-hidden A performance is documented in `APPROACH.md`.
