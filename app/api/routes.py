"""FastAPI API routes for Judicial Case Summary application."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.models import HearingSummaryData
from app.engines import get_engine
from app.generators.docx_generator import generate_docx_summary


router = APIRouter(prefix="/api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if not list(PROJECT_ROOT.glob("Proc.*")) and list(PROJECT_ROOT.parent.glob("Proc.*")):
    SAMPLES_ROOT = PROJECT_ROOT.parent
else:
    SAMPLES_ROOT = PROJECT_ROOT


@router.get("/health")
def health_check() -> Dict[str, str]:
    """Health status check."""
    return {"status": "ok", "app": "Resumo para Audiência - TJRN / PJe"}


@router.get("/samples")
def list_sample_cases() -> List[Dict[str, Any]]:
    """Lists the 9 pre-indexed reference cases available in the project root."""
    samples = []
    for p in sorted(SAMPLES_ROOT.glob("Proc.*")):
        if p.is_dir():
            pdf_file = next(p.glob("*.pdf"), None)
            docx_file = next(p.glob("*.docx"), None)
            if pdf_file:
                samples.append(
                    {
                        "folder_name": p.name,
                        "case_number": p.name.replace("Proc. ", "").strip(),
                        "pdf_name": pdf_file.name,
                        "has_reference_docx": docx_file is not None,
                        "reference_docx_name": docx_file.name if docx_file else "",
                    }
                )
    return samples


@router.post("/extract-sample")
def extract_sample_case(
    folder_name: str = Form(...),
    engine_mode: str = Form("offline"),
    api_key: Optional[str] = Form(None),
) -> HearingSummaryData:
    """Extracts a summary directly from one of the reference sample folders."""
    folder = SAMPLES_ROOT / folder_name
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Sample folder not found.")

    pdf_file = next(folder.glob("*.pdf"), None)
    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF not found in sample folder.")

    engine = get_engine(mode=engine_mode, api_key=api_key)
    try:
        data = engine.extract(str(pdf_file), api_key=api_key)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(exc)}")


@router.post("/upload")
async def upload_and_extract_pdf(
    file: UploadFile = File(...),
    engine_mode: str = Form("offline"),
    api_key: Optional[str] = Form(None),
) -> HearingSummaryData:
    """Accepts uploaded PJe PDF autos, executes extraction, and returns structured data."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser um PDF válido do PJe.")

    # Save to temporary file
    temp_dir = Path(tempfile.gettempdir()) / "pje_resumos"
    temp_dir.mkdir(exist_ok=True)
    temp_pdf = temp_dir / file.filename

    with open(temp_pdf, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        engine = get_engine(mode=engine_mode, api_key=api_key)
        data = engine.extract(str(temp_pdf), api_key=api_key)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar autos em PDF: {str(exc)}")
    finally:
        if temp_pdf.exists():
            try:
                temp_pdf.unlink()
            except OSError:
                pass


@router.post("/generate-docx")
def generate_docx_endpoint(data: HearingSummaryData) -> Response:
    """Generates and returns byte-perfect DOCX file from edited hearing summary data."""
    try:
        docx_bytes = generate_docx_summary(data)
        safe_case = data.case_number.replace("/", "-").replace(" ", "_")
        filename = f"Resumo - {safe_case} {data.act_type}.docx"

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar documento DOCX: {str(exc)}")
