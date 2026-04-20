"""PDF アップロード関連のルート。"""
import asyncio
import json
import shutil
import threading
import uuid
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, File, Form, HTTPException, UploadFile

from api.core.status_codes import StatusCode
from api.database.job_service import JobService
from api.models.job import JobCreateResponse, JobStatus

from ._pipeline import convert_pdf_to_slides
from ._shared import (
    ALLOWED_PROVIDERS,
    KNOWLEDGE_MAX_BYTES,
    PDF_MAX_BYTES,
    SPEAKER_ID_RANGE,
    SPEAKER_SPEED_RANGE,
    TARGET_DURATION_RANGE,
    UPLOAD_DIR,
    router,
    sanitize_filename,
)


@router.post("/upload", response_model=JobCreateResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_duration: int = Form(10),
    speaker1_id: int = Form(2),
    speaker1_name: str = Form("四国めたん"),
    speaker1_speed: float = Form(1.0),
    speaker2_id: int = Form(3),
    speaker2_name: str = Form("ずんだもん"),
    speaker2_speed: float = Form(1.0),
    conversation_style: str = Form("friendly"),
    conversation_style_prompt: str = Form(""),
    knowledge_file: UploadFile = File(None),
    api_key: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
):
    """PDFファイルをアップロードしてジョブを作成。"""

    safe_pdf_name = sanitize_filename(file.filename, "PDF")
    if not safe_pdf_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルのみ対応しています")

    if file.size and file.size > PDF_MAX_BYTES:
        raise HTTPException(status_code=413, detail="ファイルサイズが大きすぎます（最大100MB）")

    if not (TARGET_DURATION_RANGE[0] <= target_duration <= TARGET_DURATION_RANGE[1]):
        raise HTTPException(status_code=400, detail="target_duration は 1〜120 分の範囲で指定してください")
    if not (SPEAKER_ID_RANGE[0] <= speaker1_id <= SPEAKER_ID_RANGE[1] and
            SPEAKER_ID_RANGE[0] <= speaker2_id <= SPEAKER_ID_RANGE[1]):
        raise HTTPException(status_code=400, detail="speaker_id が範囲外です")
    if not (SPEAKER_SPEED_RANGE[0] <= speaker1_speed <= SPEAKER_SPEED_RANGE[1] and
            SPEAKER_SPEED_RANGE[0] <= speaker2_speed <= SPEAKER_SPEED_RANGE[1]):
        raise HTTPException(status_code=400, detail="speaker_speed は 0.5〜2.0 の範囲で指定してください")
    if provider is not None and provider != "" and provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider は {sorted(ALLOWED_PROVIDERS)} のいずれかを指定してください",
        )

    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    pdf_path = job_dir / safe_pdf_name
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # PDF マジックナンバー検証
    try:
        with open(pdf_path, "rb") as fh:
            header = fh.read(5)
    except OSError:
        header = b""
    if header != b"%PDF-":
        try:
            pdf_path.unlink()
            job_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="有効なPDFファイルではありません")

    knowledge_text = ""
    if knowledge_file and knowledge_file.filename:
        safe_knowledge_name = sanitize_filename(knowledge_file.filename, "ナレッジ")
        if knowledge_file.size and knowledge_file.size > KNOWLEDGE_MAX_BYTES:
            raise HTTPException(status_code=413, detail="ナレッジファイルが大きすぎます（最大10MB）")
        knowledge_path = job_dir / safe_knowledge_name
        with open(knowledge_path, "wb") as buffer:
            shutil.copyfileobj(knowledge_file.file, buffer)
        try:
            # lazy: python-docx などオプション依存を取り込むため
            from api.core.knowledge_extractor import extract_text_from_knowledge_file
            knowledge_text = extract_text_from_knowledge_file(str(knowledge_path))
        except Exception as e:
            print(f"ナレッジファイルの処理エラー: {e}")
            knowledge_text = ""

    metadata = {
        "original_pdf_filename": safe_pdf_name,
        "target_duration": target_duration,
        "speaker1": {"id": speaker1_id, "name": speaker1_name, "speed": speaker1_speed},
        "speaker2": {"id": speaker2_id, "name": speaker2_name, "speed": speaker2_speed},
        "conversation_style": conversation_style,
        "conversation_style_prompt": conversation_style_prompt,
        "additional_knowledge": knowledge_text,
        "api_key": api_key,
        "provider": provider,
    }

    JobService.create_job(
        job_id=job_id,
        status="pending",
        status_code=StatusCode.PDF_UPLOADING,
        target_duration=target_duration,
        metadata=metadata,
    )

    # 後方互換: メタデータをファイルに保存
    metadata_file = job_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    target_duration_file = job_dir / "target_duration.txt"
    with open(target_duration_file, "w") as f:
        f.write(str(target_duration))

    # バックグラウンドでPDF変換
    def run_in_thread():
        asyncio.run(convert_pdf_to_slides(job_id, str(pdf_path), target_duration, metadata, api_key, provider))

    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True
    thread.start()

    return JobCreateResponse(job_id=job_id)
