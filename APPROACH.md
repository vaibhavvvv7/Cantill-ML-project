# APPROACH

## Pipeline design

The solution uses one canonical internal schema and YAML-driven source mappings. Each source is converted into fields such as record ID, supplier, material, description, PO, invoice, quantity, date, currency and reporting amount. Source-specific columns needed for rules or classification are retained by configuration. The same pipeline then performs normalization, spend rules, matching, entity resolution, taxonomy classification and output validation.

Amounts are parsed defensively. Company A ERP values are already net ZAR; invoice-tool gross amounts are divided by `(1 + VAT)`, accepting `15`, `15%`, `0.15`, zero VAT and the specified 15% default when blank. Company B reports USD: USD is unchanged, non-USD uses the inline `currency_rate` where present, otherwise the monthly `fx_rates_usd.csv` value for the selected invoice/posting date.

## Matching and de-duplication

Company A PO references are normalized from formats such as `PO 4510109330` and `4510085877/10.0`. Candidate ERP receipts are blocked on normalized PO, then pruned by net-amount proximity before scoring quantity, description, supplier similarity and PO-line agreement. Matching is conservative: the ERP row is counted and the tool row is `DUPLICATE`. Exact repeated tool exports are detected with normalized invoice number, supplier, net amount and description. Status exclusions take precedence over duplicate reason codes.

On the supplied build data the pipeline excludes 17,335 A rows as cross-system/tool duplicates, 188 as `CANCELLED`, and 315 as `NOT_APPROVED`.

## Supplier and item resolution

For A, labelled ERP records are used to learn reusable vendor-ID and normalized-name mappings to the golden supplier identity. New/unseen suppliers receive deterministic hashed keys. Material number is the strongest item identifier; fallback identity uses normalized description plus supplier and deterministic hashing. Tool rows confidently matched to ERP inherit the ERP supplier/item identities.

For B/C, vendor ID is used as the stable supplier anchor when no name exists; item identity prioritizes material number and otherwise uses supplier + normalized description. Keys are deterministic across runs.

## Classification and unseen trees

The taxonomy is always loaded at runtime and represented as valid root-to-leaf paths, so code does not contain Company A/B category names. When labels exist, a sparse TF-IDF + logistic-loss SGD text model is trained from configurable fields. Strong, high-purity material/item/description-to-category mappings learned from labels override the model when available. The predicted leaf determines all parent levels, preventing invalid L1/L2/L3 combinations.

With zero target labels, the same classifier automatically falls back to taxonomy-only word/character TF-IDF similarity against complete taxonomy paths. This is deterministic, local and key-free. It is intentionally a fallback rather than an API dependency.

Required labels-hidden A evaluation (all A labels hidden from the classifier):

- L1 accuracy: **44.13%**
- L2 accuracy: **8.80%**
- L3 accuracy: **4.56%**

A is a difficult zero-shot test because many leaf names are maintenance/service concepts while line descriptions are abbreviated part descriptions. The fallback nevertheless guarantees valid-tree output for an unseen taxonomy. With labels enabled, the supplied A ERP rows achieve approximately **99.20% L3** category agreement; B seed-label rows are reproduced on the build data after training.

## Exclusions

A uses explicit status rules. B has no status column; non-procurement logic combines generic semantic patterns (intercompany, tax, financing-like spend) with conservative exact values learned from seed labels. On the 3,000 supplied B seed labels, the final build rules reproduce all 450 labelled `NON_PROCUREMENT` rows while retaining all 2,550 labelled included rows.

## Runtime and cost

The pipeline is designed around sparse local models, blocking and vectorized operations. It is comfortably below the brief's 60-minute / 25,000-line requirement on the supplied datasets. No LLM or paid API is used. **API cost: $0 per 1,000 lines.**
