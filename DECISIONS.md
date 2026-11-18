# DECISIONS

This file records assumptions made where the brief/data require judgement.

## 1. Canonical schema and configuration

All sources are converted to a shared internal representation before business logic. A source config maps raw fields to canonical fields and can retain extra raw columns for spend rules/classification. A new company should therefore require only a new YAML file unless it introduces a genuinely new amount/currency semantic not expressible by the existing config.

## 2. Amounts and VAT

- Company A ERP `value_zar` is treated as net spend exactly as stated in the brief.
- Company A tool `gross_amount` is parsed after removing thousands separators and then converted to net.
- `vat_rate` values `15`, `15%` and `0.15` are all interpreted as 15%.
- Blank tool VAT uses the required 15% default.
- A literal zero VAT remains zero.
- Negative values remain negative because credits/reversals may be economically meaningful.

## 3. Dates

Configured date fields are tried in priority order. Parsing errors do not crash the run. If a raw date exists but cannot be parsed, `date_parse_failed` is counted in diagnostics.

For B the priority is `invoice_date`, then `posting_date`. Monthly FX fallback uses the resulting month. Where neither an inline non-USD rate nor a monthly fallback exists, the record is retained and counted in the `fx_missing` diagnostic rather than silently inventing a rate.

## 4. Currency

The B brief defines `currency_rate` as units of line currency per USD, therefore:

`USD spend = line_amount / currency_rate`

USD lines are already USD and are never divided by a rate. Missing non-USD inline rates use `fx_rates_usd.csv` for the selected month.

The supplied B build data contains five rows for which no configured fallback rate is available; these are surfaced in diagnostics.

## 5. Approval and cancellation

A invoice-tool statuses observed are Paid, Approved, Cancelled, On Hold and Rejected.

- Paid / Approved -> eligible spend candidate
- Cancelled -> `CANCELLED`
- On Hold / Rejected -> `NOT_APPROVED`

A ERP receipts have no invoice approval status in this file and are treated as eligible procurement records.

B contains no equivalent status field, so no status rule is applied merely because the canonical schema contains an empty placeholder column.

## 6. Exclusion precedence

If a record satisfies more than one exclusion condition, the order is:

1. `CANCELLED`
2. `NOT_APPROVED`
3. `NON_PROCUREMENT`
4. `DUPLICATE`

In particular, a rejected/cancelled A tool record that also matches ERP retains its business-status reason rather than being overwritten to `DUPLICATE`.

## 7. Company A cross-system matching

PO references are normalized by extracting the main numeric PO and, where present, a suffix line number. Tool rows are blocked to ERP rows on PO to avoid all-to-all fuzzy matching.

A candidate must be within 5% of net amount before text/supplier comparison. Only the closest few amount candidates are scored. The score combines amount similarity, quantity, description token similarity, supplier-name similarity and PO-line agreement. Thresholds are deliberately conservative to reduce false duplicate declarations.

When matched, ERP is the counted record and the tool record is excluded as `DUPLICATE`, as required by the brief.

## 8. Tool-to-tool duplicate exports

A second tool row is considered a duplicate only when it has a non-blank normalized invoice number and the normalized invoice number, supplier, net amount and line description match an earlier export. This avoids collapsing unrelated blank-invoice rows.

## 9. Supplier identity

A labelled ERP data is used to learn high-purity mappings from vendor IDs and normalized supplier names to the golden identity. Normalization removes punctuation/case and common legal suffixes only for comparison. Unseen suppliers receive a deterministic SHA1-derived key.

B has no supplier names, so vendor ID is the strongest available supplier identity and is used directly as the stable input to deterministic keys.

## 10. Item identity

Material number is treated as the strongest stable item anchor when present. For A, high-purity mappings from material number and descriptions to labelled item identities are learned. For rows without a reliable material code, supplier + normalized description is used before deterministic fallback hashing.

Digits and part-number characters are deliberately preserved during normalization because strings such as sizes, power ratings and part numbers distinguish real items.

## 11. Non-procurement spend

The brief leaves exact account logic to the candidate. The implementation uses two layers:

1. generic text patterns for intercompany, tax, royalties/partner billing and financing-like charges;
2. for labelled companies, conservative exact values learned only when a field value is consistently excluded in seed labels.

In B, seed labels clearly identify intercompany descriptions such as `IC06`, `IC Payables`, `I/C Payable`, and tax descriptions such as `State & Local Taxes` / `GST Input Tax` as non-procurement. The final rules reproduce the supplied B seed exclusion decisions without excluding any seed-labelled procurement rows.

## 12. Blank descriptions

Blank text does not cause row loss. Classification can still use configured material number, GL/account, supplier/vendor, document type, source system, region, plant and cost centre fields. If there are no labels, taxonomy-only similarity may be low and confidence reflects that uncertainty.

## 13. Classification

Taxonomy paths are read at runtime and must be emitted exactly as present in the taxonomy file. The model predicts a leaf path rather than independent levels, so it cannot construct an invalid parent/child combination.

With labels, learned exact high-purity material/item/description mappings are preferred, then the supervised sparse text model. Without labels, the local taxonomy-similarity fallback is used.

## 14. Confidence

Confidence is not treated as a calibrated probability. For supervised classification it is based on the model's winning class probability transformed into a conservative 0-1 score. For taxonomy-only classification it combines best similarity and margin over the second-best path. Learned high-purity exact mappings receive high confidence.

## 15. Unparseable amounts

There is no exclusion code in the brief specifically for malformed/missing numeric amount. Such rows are retained rather than assigned a misleading reason code; their reporting spend becomes zero through output-safe handling and they are counted in `amount_parse_failures` diagnostics for manual review.
