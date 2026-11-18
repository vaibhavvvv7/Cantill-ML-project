# Cantill Spend Pipeline

A config-driven procurement spend pipeline for the Cantill.ai Data & ML task.

It ingests heterogeneous purchasing systems, normalizes amounts/dates/currency, applies spend exclusions, de-duplicates cross-system records, resolves supplier/item identities, classifies included spend into a taxonomy loaded at run time, and writes the exact required submission schema.

## Key Design Constraints

- **New company = new YAML config, not new Python code.**
- Taxonomy names are read from CSV at run time; no A/B category names are embedded in the classifier.
- Company A's ERP is the primary source when an invoice-tool row matches it.
- Company B converts to USD using inline rates first, then monthly FX fallback.
- Labels are optional. If absent, the classifier automatically falls back to taxonomy-only classification.
- Confidential task CSVs are ignored by Git and are never copied into the repository.

## Repository Layout

```text
Cantill-ML-project/
├── configs/
│   ├── company_a.yaml
│   ├── company_b.yaml
│   └── company_c_template.yaml
├── spend_pipeline/
│   ├── cli.py
│   ├── config.py
│   ├── ingest.py
│   ├── normalize.py
│   ├── spend_rules.py
│   ├── matching.py
│   ├── entities.py
│   ├── taxonomy.py
│   ├── classifier.py
│   ├── pipeline.py
│   └── evaluate.py
├── scripts/
│   ├── run_all.ps1
│   ├── run_all.sh
│   ├── evaluate_outputs.py
│   └── validate_submission.py
├── tests/
│   ├── test_fx.py
│   ├── test_matching.py
│   ├── test_normalize.py
│   ├── test_rules.py
│   ├── test_rules_no_status.py
│   └── test_taxonomy.py
├── outputs/
│   ├── vaibhav__A.csv
│   ├── vaibhav__B.csv
│   ├── A_diagnostics.json
│   ├── B_diagnostics.json
│   └── A_zero_label_metrics.json
├── submission/
├── APPROACH.md
├── BLIND_TEST.md
├── DECISIONS.md
├── README.md
├── pyproject.toml
├── pytest.ini
├── requirements.txt
└── .gitignore
```

---

## Quick Start & Setup

### 1. Clone & Environment

Python 3.10+ is recommended.

**Windows PowerShell:**
```powershell
git clone https://github.com/vaibhavvvv7/Cantill-ML-project.git
cd Cantill-ML-project

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

**Linux / macOS:**
```bash
git clone https://github.com/vaibhavvvv7/Cantill-ML-project.git
cd Cantill-ML-project

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Task Data Placement

The project code intentionally does not contain the confidential source CSVs. Place the original Cantill kit in the repository root under `data/`:

```text
cantill_project/
├── configs/
├── spend_pipeline/
├── tests/
├── outputs/
├── requirements.txt
└── data/
    └── Cantill_DataML_Task_Kit/
        ├── company_A/
        ├── company_B/
        └── output_template.csv
```

The `data/` directory is automatically ignored by `.gitignore`.

Alternatively, if your extracted task kit is located elsewhere, pass its location using `--data-root`:
```powershell
--data-root "C:\path\to\Cantill_DataML_Task_Kit"
```
Or set the `CANTILL_DATA_ROOT` environment variable.

---

## Running the Pipeline

### Run Company A

**Windows PowerShell:**
```powershell
python -m spend_pipeline `
  --config configs/company_a.yaml `
  --output outputs\vaibhav__A.csv
```

**Linux / macOS:**
```bash
python -m spend_pipeline \
  --config configs/company_a.yaml \
  --output outputs/vaibhav__A.csv
```

- Ingests ERP goods receipts and invoice-tool exports.
- Applies VAT normalization, status exclusions (`CANCELLED`, `NOT_APPROVED`), ERP-to-tool cross-system deduplication, and supplier/item identity resolution.
- Classifies eligible spend into taxonomy paths and writes the submission file.
- **Expected build-data row count:** `65,549` (37,029 ERP + 28,520 tool).

### Run Company B

**Windows PowerShell:**
```powershell
python -m spend_pipeline `
  --config configs/company_b.yaml `
  --output outputs\vaibhav__B.csv
```

**Linux / macOS:**
```bash
python -m spend_pipeline \
  --config configs/company_b.yaml \
  --output outputs/vaibhav__B.csv
```

- Converts line amounts to USD using inline rates with monthly FX fallback.
- Detects non-procurement charges (intercompany, taxes, fees).
- Resolves identities and classifies spend.
- **Expected build-data row count:** `41,028`.

### Run Both Companies

- **Windows PowerShell:** `.\scripts\run_all.ps1`
- **Linux / macOS:** `./scripts/run_all.sh`

---

## Running the Tests

```bash
pytest -q
```

**Expected result:** `7 passed`

Tests cover:
- Gross/net amount and VAT normalization
- PO reference normalization and line extraction
- Approval and cancellation status rules
- Status vs. duplicate exclusion precedence
- Multi-currency USD conversion and FX monthly fallbacks
- Taxonomy tree validation and zero-label fallback matching

---

## Zero-Label Mode & Evaluation

To test classification when labels are absent (forcing the deterministic lexical fallback):

```powershell
python -m spend_pipeline `
  --config configs/company_a.yaml `
  --output outputs\A_zero_label.csv `
  --no-labels
```

Measure the required labels-hidden Company A evaluation:

```powershell
python -m spend_pipeline.evaluate `
  --config configs/company_a.yaml
```

---

## Blind-Test Procedure (Company C)

When Company C is provided, the Python codebase remains frozen. Only configuration is added:

1. Copy the template:
```powershell
# Windows PowerShell
Copy-Item configs\company_c_template.yaml configs\company_c.yaml

# Linux / macOS
cp configs/company_c_template.yaml configs/company_c.yaml
```

2. Edit `configs/company_c.yaml` with Company C's schema:
- Input filename & taxonomy filename
- Taxonomy level columns (L1–L4)
- Raw-to-canonical column mappings (supplier, item, description, amount, currency, dates)
- Spend status rules and FX fallback if required

3. Execute the unchanged pipeline:
```powershell
python -m spend_pipeline `
  --config configs/company_c.yaml `
  --data-root "C:\path\to\blind_test_data" `
  --output submission\vaibhav__C.csv
```

4. Validate the submission file:
```powershell
python scripts/validate_submission.py submission\vaibhav__C.csv
```

See [`BLIND_TEST.md`](file:///c:/Users/shiva/OneDrive/Desktop/cantill_project/BLIND_TEST.md) for the timed checklist.

---

## Output Schema

Every input record is preserved in the submission file, including excluded rows:

```text
record_id,include,exclusion_reason,supplier_key,item_key,spend,l1,l2,l3,l4,confidence
```

Validation guarantees before writing:
- Row count matches input row count exactly.
- `record_id` is unique.
- Excluded rows have `spend = 0.0`.
- Valid exclusion codes (`CANCELLED`, `NOT_APPROVED`, `NON_PROCUREMENT`, `DUPLICATE`).
- Included rows have empty `exclusion_reason`.
- Confidence score is bounded in $[0.0, 1.0]$.
- Every category path strictly exists in the runtime taxonomy.

---

## Runtime and Cost

- **API Cost:** **$0 per 1,000 lines** (key-free, runs fully locally).
- **Execution Speed:** Vectorized and sparse text representations ensure runs finish in minutes, well below the 60-minute threshold.
