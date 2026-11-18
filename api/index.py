from __future__ import annotations
import sys
import os
import json
import time
import uuid
import tempfile
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

# In-memory store for generated downloads: {task_id: {"content": bytes, "filename": str, "created_at": float}}
DOWNLOAD_CACHE: dict[str, dict] = {}


def _cleanup_cache():
    now = time.time()
    expired = [k for k, v in DOWNLOAD_CACHE.items() if now - v.get("created_at", 0) > 3600]
    for k in expired:
        DOWNLOAD_CACHE.pop(k, None)


def _is_valid_upload(f) -> bool:
    return f is not None and hasattr(f, "read") and bool(getattr(f, "filename", ""))


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    html_path = ROOT_DIR / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Cantill Spend Pipeline is Running</h2><p>Visit <a href='/api/health'>/api/health</a> or inspect GitHub repository.</p>")


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "engine": "Cantill Spend Pipeline",
        "author": "Vaibhav",
        "repository": "https://github.com/vaibhavvvv7/Cantill-ML-project"
    }


@app.get("/api/demo/{company}")
async def get_demo_diagnostics(company: str):
    comp = company.upper()
    diag_file = ROOT_DIR / "outputs" / f"{comp}_diagnostics.json"
    if not diag_file.exists():
        raise HTTPException(status_code=404, detail=f"No pre-computed diagnostics found for Company {comp}")
    return json.loads(diag_file.read_text(encoding="utf-8"))


@app.get("/api/demo/{company}/download")
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


@app.post("/api/run")
async def run_pipeline_endpoint(request: Request):
    try:
        from spend_pipeline.pipeline import run_pipeline
    except ImportError as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": f"ML pipeline dependencies not ready: {str(e)}"
        })

    try:
        form = await request.form()
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": f"Failed to parse form data. Ensure python-multipart is installed: {str(e)}"
        })

    company = str(form.get("company", "A")).strip().upper()
    if company not in {"A", "B", "C"}:
        return JSONResponse(status_code=400, content={"success": False, "error": f"Invalid company: {company}"})

    raw_labels = form.get("use_labels", "true")
    use_labels = str(raw_labels).lower() in ["true", "1", "on", "yes"]

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

        if company == "A":
            if not _is_valid_upload(erp_file) or not _is_valid_upload(tool_file) or not _is_valid_upload(taxonomy_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company A requires: ERP CSV, Invoice Tool CSV, and Taxonomy CSV."
                })

            comp_dir = tmp_path / "company_A"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "erp_goods_receipts.csv").write_bytes(await erp_file.read())
            (comp_dir / "invoice_tool_export.csv").write_bytes(await tool_file.read())
            (comp_dir / "taxonomy_A.csv").write_bytes(await taxonomy_file.read())
            if _is_valid_upload(labels_file):
                (comp_dir / "labels_A.csv").write_bytes(await labels_file.read())
            else:
                use_labels = False

            config_path = str(ROOT_DIR / "configs" / "company_a.yaml")

        elif company == "B":
            if not _is_valid_upload(invoice_file) or not _is_valid_upload(taxonomy_file) or not _is_valid_upload(fx_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company B requires: Invoice Lines CSV, Taxonomy CSV, and FX Rates CSV."
                })

            comp_dir = tmp_path / "company_B"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "invoice_lines.csv").write_bytes(await invoice_file.read())
            (comp_dir / "taxonomy_B.csv").write_bytes(await taxonomy_file.read())
            (comp_dir / "fx_rates_usd.csv").write_bytes(await fx_file.read())
            if _is_valid_upload(labels_file):
                (comp_dir / "seed_labels.csv").write_bytes(await labels_file.read())
            else:
                use_labels = False

            config_path = str(ROOT_DIR / "configs" / "company_b.yaml")

        else:  # Company C
            if not _is_valid_upload(invoice_file) or not _is_valid_upload(taxonomy_file):
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "Company C requires: Invoice Lines CSV and Taxonomy CSV."
                })

            comp_dir = tmp_path / "company_C"
            comp_dir.mkdir(parents=True, exist_ok=True)

            (comp_dir / "invoice_lines.csv").write_bytes(await invoice_file.read())
            (comp_dir / "taxonomy_C.csv").write_bytes(await taxonomy_file.read())

            if _is_valid_upload(config_file):
                cfg_path = tmp_path / "company_c.yaml"
                cfg_path.write_bytes(await config_file.read())
                config_path = str(cfg_path)
            else:
                config_path = str(ROOT_DIR / "configs" / "company_c_template.yaml")

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
            return JSONResponse(status_code=500, content={
                "success": False,
                "error": f"Pipeline processing failed: {str(e)}"
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
