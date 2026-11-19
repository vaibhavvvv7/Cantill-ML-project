from __future__ import annotations
import sys
import os
import json
import time
import uuid
import tempfile
import traceback
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Cantill Spend Pipeline API",
    description="Config-driven procurement spend normalization, deduplication & taxonomy classification",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def fix_vercel_path(request: Request, call_next):
    """Normalize Vercel rewrite paths so FastAPI router correctly dispatches requests."""
    scope = request.scope
    headers = dict(request.headers)

    # If Vercel passed the original matched path in headers, use it
    matched_path = headers.get("x-matched-path")
    if matched_path and matched_path not in ("/api/index.py", "/api/index", "/index.py"):
        scope["path"] = matched_path
    else:
        path = scope.get("path", "")
        for prefix in ("/api/index.py", "/api/index", "/index.py"):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                scope["path"] = remainder if remainder else "/"
                break

    response = await call_next(request)
    return response


# In-memory store for generated downloads: {task_id: {"content": bytes, "filename": str, "created_at": float}}
DOWNLOAD_CACHE: dict[str, dict] = {}

# Embedded default configs as fallback if not bundled in serverless environment
DEFAULT_CONFIGS = {
    "A": """company: A
data_root: data/Cantill_DataML_Task_Kit
reporting_currency: ZAR

taxonomy:
  file: company_A/taxonomy_A.csv
  columns: [category_l1, category_l2, category_l3]

labels:
  file: company_A/labels_A.csv
  id_column: record_id
  id_prefix: ""
  category_columns: [category_l1, category_l2, category_l3]

sources:
  - name: ERP
    file: company_A/erp_goods_receipts.csv
    id_column: line_id
    record_prefix: "ERP:"
    columns:
      supplier_id: vendor_id
      supplier_name: supplier_name
      material_id: material_number
      currency: document_currency
      quantity: quantity
      po_number: po_number
      po_line: po_item
    description_columns: [material_short_text, service_short_text]
    date_columns: [posting_date]
    amount:
      column: value_zar
      type: net
    retain_columns: [source_system, spend_type, material_type, uom, site_code, site_name, cost_centre, opex_capex, contract_status]

  - name: TOOL
    file: company_A/invoice_tool_export.csv
    id_column: tool_record_id
    record_prefix: "TOOL:"
    columns:
      supplier_name: supplier_name_as_captured
      status: status
      currency: currency
      quantity: quantity
      po_number: po_reference
      invoice_number: invoice_number
    description_columns: [line_text]
    date_columns: [invoice_date]
    amount:
      column: gross_amount
      type: gross
      tax_column: vat_rate
      default_tax: 0.15

matching:
  enabled: true
  primary_source: ERP
  secondary_source: TOOL

spend_rules:
  status_column: status
  approved_statuses: [Paid, Approved, ""]
  cancelled_statuses: [Cancelled]
  non_procurement_text_columns: []

classification:
  feature_columns: [description, material_id, supplier_name, supplier_id, spend_type, material_type, cost_centre, site_code]
""",
    "B": r"""company: B
data_root: data/Cantill_DataML_Task_Kit
reporting_currency: USD

taxonomy:
  file: company_B/taxonomy_B.csv
  columns: [category_l1, category_l2, category_l3]

labels:
  file: company_B/seed_labels.csv
  id_column: line_id
  id_prefix: ""
  category_columns: [category_l1, category_l2, category_l3]

sources:
  - name: AP
    file: company_B/invoice_lines.csv
    id_column: line_id
    record_prefix: ""
    columns:
      supplier_id: vendor_id
      material_id: material_number
      currency: currency
      quantity: quantity
      po_number: po_number
      po_line: po_line
      invoice_number: invoice_number
    description_columns: [line_description, gl_account_description]
    date_columns: [invoice_date, posting_date]
    amount:
      column: line_amount
      type: net
    retain_columns: [source_system, region, currency_rate, cost_centre, gl_account, gl_account_description, supplier_type, document_type, po_type, plant, company_code, payment_terms, transport_flag]

fx:
  inline_rate_column: currency_rate
  file: company_B/fx_rates_usd.csv
  currency_column: currency
  month_column: month
  rate_column: units_per_usd

spend_rules:
  learn_exact_columns: [gl_account_description, supplier_type]
  non_procurement_text_columns: [gl_account_description, line_description]
  non_procurement_regex:
    - '^IC[0-9]+$'
    - '\bI/C\s*Payable\b'
    - '\bIC\s*Payables?\b'

classification:
  feature_columns: [description, material_id, supplier_id, gl_account, gl_account_description, supplier_type, document_type, po_type, source_system, region, plant, cost_centre]
""",
    "C": """company: C
data_root: data/Cantill_DataML_Task_Kit
reporting_currency: USD

taxonomy:
  file: company_C/taxonomy_C.csv
  columns: [category_l1, category_l2, category_l3, category_l4]

sources:
  - name: AP
    file: company_C/invoice_lines.csv
    id_column: line_id
    record_prefix: ""
    columns:
      supplier_id: vendor_id
      supplier_name: supplier_name
      material_id: material_number
      status: status
      currency: currency
      quantity: quantity
      po_number: po_number
      po_line: po_line
      invoice_number: invoice_number
    description_columns: [line_description, gl_account_description]
    date_columns: [invoice_date, posting_date]
    amount:
      column: line_amount
      type: net
    retain_columns: [gl_account, gl_account_description, supplier_type, document_type, cost_centre]

spend_rules:
  status_column: status
  approved_statuses: [Approved, Paid]
  cancelled_statuses: [Cancelled, Canceled]
  non_procurement_text_columns: [gl_account_description, line_description]

classification:
  feature_columns: [description, material_id, supplier_name, supplier_id, gl_account_description, document_type, cost_centre]
"""
}


def _cleanup_cache():
    now = time.time()
    expired = [k for k, v in DOWNLOAD_CACHE.items() if now - v.get("created_at", 0) > 3600]
    for k in expired:
        DOWNLOAD_CACHE.pop(k, None)


def _is_valid_upload(f) -> bool:
    return f is not None and hasattr(f, "read") and bool(getattr(f, "filename", ""))


def _get_index_html() -> str:
    # 1. Try static/index.html from project root
    p1 = ROOT_DIR / "static" / "index.html"
    if p1.exists():
        try:
            return p1.read_text(encoding="utf-8")
        except Exception:
            pass
    # 2. Try relative to current api directory
    p2 = Path(__file__).resolve().parent.parent / "static" / "index.html"
    if p2.exists():
        try:
            return p2.read_text(encoding="utf-8")
        except Exception:
            pass
    return "<h2>Cantill Spend Pipeline is Running</h2><p>Visit <a href='/api/health'>/api/health</a> or inspect GitHub repository.</p>"


@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
@app.get("/api/", response_class=HTMLResponse)
@app.get("/api/index", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
@app.get("/index.py", response_class=HTMLResponse)
async def serve_home():
    return HTMLResponse(content=_get_index_html())


@app.get("/api/health")
@app.get("/health")
@app.get("/api/index.py/api/health")
@app.get("/api/index/api/health")
async def health_check():
    return {
        "status": "healthy",
        "engine": "Cantill Spend Pipeline",
        "author": "Vaibhav",
        "repository": "https://github.com/vaibhavvvv7/Cantill-ML-project"
    }


@app.get("/api/demo/{company}")
@app.get("/demo/{company}")
@app.get("/api/index.py/api/demo/{company}")
async def get_demo_diagnostics(company: str):
    comp = company.upper()
    diag_file = ROOT_DIR / "outputs" / f"{comp}_diagnostics.json"
    if not diag_file.exists():
        raise HTTPException(status_code=404, detail=f"No pre-computed diagnostics found for Company {comp}")
    return json.loads(diag_file.read_text(encoding="utf-8"))


@app.get("/api/demo/{company}/download")
@app.get("/demo/{company}/download")
@app.get("/api/index.py/api/demo/{company}/download")
async def download_demo_csv(company: str):
    comp = company.upper()
    csv_file = ROOT_DIR / "outputs" / f"vaibhav__{comp}.csv"
    if not csv_file.exists():
        raise HTTPException(status_code=404, detail=f"No pre-computed submission file found for Company {comp}")
    return FileResponse(
        path=str(csv_file),
        media_type="text/csv",
        filename=f"vaibhav__{comp}.csv"
    )


# Accept POST on every conceivable route variant to prevent 405 Method Not Allowed
@app.post("/api/run")
@app.post("/run")
@app.post("/")
@app.post("/api")
@app.post("/api/")
@app.post("/api/index")
@app.post("/api/index.py")
@app.post("/index.py")
@app.post("/api/index.py/api/run")
@app.post("/api/index/api/run")
async def run_pipeline_endpoint(request: Request):
    try:
        from spend_pipeline.pipeline import run_pipeline
    except ImportError as e:
        tb = traceback.format_exc()
        print("IMPORT ERROR:\n", tb)
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": f"ImportError: {str(e)}",
            "detail": f"Dependencies missing: {str(e)}",
            "traceback": tb
        })

    try:
        form = await request.form()
    except Exception as e:
        tb = traceback.format_exc()
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": f"FormDataError: {str(e)}",
            "detail": f"Failed to parse multipart form: {str(e)}",
            "traceback": tb
        })

    company = str(form.get("company", "A")).strip().upper()
    if company not in {"A", "B", "C"}:
        return JSONResponse(status_code=400, content={"success": False, "error": f"Invalid company: {company}"})

    raw_labels = form.get("use_labels", "true")
    user_wants_labels = str(raw_labels).lower() in ["true", "1", "on", "yes"]

    erp_file = form.get("erp_file")
    tool_file = form.get("tool_file")
    invoice_file = form.get("invoice_file")
    taxonomy_file = form.get("taxonomy_file")
    fx_file = form.get("fx_file")
    labels_file = form.get("labels_file")
    config_file = form.get("config_file")

    _cleanup_cache()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Ensure configs directory exists in temp dir
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        if company == "A":
            if not _is_valid_upload(erp_file) or not _is_valid_upload(tool_file) or not _is_valid_upload(taxonomy_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company A requires: ERP CSV, Invoice Tool CSV, and Taxonomy CSV.",
                    "detail": "Missing one of the required CSV files for Company A."
                })

            comp_dir = tmp_path / "company_A"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "erp_goods_receipts.csv").write_bytes(await erp_file.read())
            (comp_dir / "invoice_tool_export.csv").write_bytes(await tool_file.read())
            (comp_dir / "taxonomy_A.csv").write_bytes(await taxonomy_file.read())

            if _is_valid_upload(labels_file) and user_wants_labels:
                (comp_dir / "labels_A.csv").write_bytes(await labels_file.read())
                use_labels = True
            else:
                use_labels = False

            # Prepare config file
            cfg_file = cfg_dir / "company_a.yaml"
            cfg_file.write_text(DEFAULT_CONFIGS["A"], encoding="utf-8")
            config_path = str(cfg_file)

        elif company == "B":
            if not _is_valid_upload(invoice_file) or not _is_valid_upload(taxonomy_file) or not _is_valid_upload(fx_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company B requires: Invoice Lines CSV, Taxonomy CSV, and FX Rates CSV.",
                    "detail": "Missing one of the required CSV files for Company B."
                })

            comp_dir = tmp_path / "company_B"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "invoice_lines.csv").write_bytes(await invoice_file.read())
            (comp_dir / "taxonomy_B.csv").write_bytes(await taxonomy_file.read())
            (comp_dir / "fx_rates_usd.csv").write_bytes(await fx_file.read())

            if _is_valid_upload(labels_file) and user_wants_labels:
                (comp_dir / "seed_labels.csv").write_bytes(await labels_file.read())
                use_labels = True
            else:
                use_labels = False

            cfg_file = cfg_dir / "company_b.yaml"
            cfg_file.write_text(DEFAULT_CONFIGS["B"], encoding="utf-8")
            config_path = str(cfg_file)

        else:  # Company C
            if not _is_valid_upload(invoice_file) or not _is_valid_upload(taxonomy_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company C requires: Invoice Lines CSV and Taxonomy CSV.",
                    "detail": "Missing one of the required CSV files for Company C."
                })

            comp_dir = tmp_path / "company_C"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "invoice_lines.csv").write_bytes(await invoice_file.read())
            (comp_dir / "taxonomy_C.csv").write_bytes(await taxonomy_file.read())

            cfg_file = cfg_dir / "company_c.yaml"
            if _is_valid_upload(config_file):
                cfg_file.write_bytes(await config_file.read())
            else:
                cfg_file.write_text(DEFAULT_CONFIGS["C"], encoding="utf-8")
            config_path = str(cfg_file)

            use_labels = False

        output_file = tmp_path / f"vaibhav__{company}.csv"
        diag_file = tmp_path / f"{company}_diagnostics.json"

        try:
            _, diag = run_pipeline(
                config_path=config_path,
                output_path=str(output_file),
                data_root=str(tmp_path),
                use_labels=use_labels,
                diagnostics_path=str(diag_file)
            )
            csv_bytes = output_file.read_bytes()
        except Exception as e:
            tb = traceback.format_exc()
            print("PIPELINE RUNTIME EXCEPTION:\n", tb)
            return JSONResponse(status_code=500, content={
                "success": False,
                "error": f"{type(e).__name__}: {str(e)}",
                "detail": f"{type(e).__name__}: {str(e)}",
                "traceback": tb
            })

    download_id = str(uuid.uuid4())
    filename = f"vaibhav__{company}.csv"
    DOWNLOAD_CACHE[download_id] = {
        "content": csv_bytes,
        "filename": filename,
        "created_at": time.time()
    }

    return {
        "success": True,
        "diagnostics": diag,
        "download_id": download_id,
        "filename": filename
    }


@app.get("/api/download/{download_id}")
@app.get("/download/{download_id}")
@app.get("/api/index.py/api/download/{download_id}")
async def download_result(download_id: str):
    item = DOWNLOAD_CACHE.get(download_id)
    if not item:
        raise HTTPException(status_code=404, detail="Download expired or not found. Please re-run the pipeline.")
    return Response(
        content=item["content"],
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{item["filename"]}"'
        }
    )


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    path = request.scope.get("path", "")
    # If the user accessed the root or an edge path, serve the home interface
    if not path.startswith("/api/") or "index.py" in path or path in ("/api", "/api/"):
        return await serve_home()
    return JSONResponse(status_code=404, content={"detail": f"Not Found: {path}"})
