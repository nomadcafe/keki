"""ジョブの CRUD（一覧・ステータス・削除・メタデータ）ルート。"""
import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Query

from api.database.job_service import JobService
from api.models.job import JobStatus

from ._shared import OUTPUT_DIR, UPLOAD_DIR, jobs_db, router


@router.get("/{job_id}/status", response_model=JobStatus)
async def get_job_status(job_id: str):
    """ジョブのステータスを取得。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return jobs_db[job_id]


@router.get("")
async def list_jobs(
    limit: Optional[int] = Query(None, description="取得件数"),
    offset: int = Query(0, ge=0, description="オフセット"),
    status: Optional[str] = Query(None, description="ステータスでフィルタ"),
):
    """ジョブ一覧を取得（履歴画面用）。"""
    return JobService.list_jobs_dict(limit=limit, offset=offset, status=status)


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """ジョブを削除。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job_dir = UPLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)

    output_file = OUTPUT_DIR / f"{job_id}.mp4"
    if output_file.exists():
        output_file.unlink()

    del jobs_db[job_id]
    return {"message": "ジョブを削除しました"}


@router.get("/{job_id}/metadata")
async def get_job_metadata(job_id: str):
    """ジョブのメタデータを取得。"""
    metadata_path = UPLOAD_DIR / job_id / "metadata.json"
    if not metadata_path.exists():
        return {
            "speaker1": {"id": 2, "name": "四国めたん"},
            "speaker2": {"id": 3, "name": "ずんだもん"},
            "target_duration": 10,
        }
    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/{job_id}/instruction-history")
async def get_instruction_history(job_id: str):
    """指示履歴を取得。"""
    from api.core.instruction_history import InstructionHistory

    history = InstructionHistory(job_id, Path.cwd())
    return {"history": history.history}
