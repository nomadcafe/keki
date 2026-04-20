"""音声生成・動画作成のルート。"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Form, HTTPException

from api.core.async_worker import async_worker
from api.core.status_codes import StatusCode
from api.database.job_service import JobService
from api.models.job import CreateVideoRequest, GenerateAudioRequest

from ._pipeline import create_video_task, generate_audio_task, generate_complete_video
from ._shared import jobs_db, router


@router.post("/{job_id}/generate-audio")
async def generate_audio(
    job_id: str,
    request: GenerateAudioRequest,
    background_tasks: BackgroundTasks,
):
    """音声生成を開始。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs_db[job_id]
    if job.status not in ["slides_ready", "dialogue_ready"]:
        raise HTTPException(
            status_code=400,
            detail="スライド変換または対話スクリプトの準備が完了していません",
        )

    job.status = "generating_audio"
    job.status_code = StatusCode.AUDIO_GENERATING
    job.progress = 30
    job.updated_at = datetime.now()

    background_tasks.add_task(
        generate_audio_task,
        job_id,
        request.speed_scale,
        request.pitch_scale,
        request.intonation_scale,
        request.volume_scale,
    )
    return {"message": "音声生成を開始しました"}


@router.post("/{job_id}/create-video")
async def create_video(
    job_id: str,
    request: CreateVideoRequest,
    background_tasks: BackgroundTasks,
):
    """動画作成を開始。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs_db[job_id]
    if job.status != "audio_ready":
        raise HTTPException(status_code=400, detail="音声生成が完了していません")

    job.status = "creating_video"
    job.status_code = StatusCode.VIDEO_CREATING
    job.progress = 70
    job.updated_at = datetime.now()

    background_tasks.add_task(
        create_video_task,
        job_id,
        request.slide_numbers,
        request.bgm_enabled,
        request.bgm_path,
        request.bgm_volume,
        request.transition_type,
        request.transition_duration,
    )
    return {"message": "動画作成を開始しました"}


@router.post("/{job_id}/generate-video")
async def generate_video_complete(
    job_id: str,
    background_tasks: BackgroundTasks,
    bgm_enabled: bool = Form(False),
    bgm_path: Optional[str] = Form(None),
    bgm_volume: float = Form(0.15),
    transition_type: str = Form("crossfade"),
    transition_duration: float = Form(0.4),
):
    """ワンクリック動画生成（全工程を自動実行・非同期処理）。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs_db[job_id]
    if job.status not in ["pending", "slides_ready", "dialogue_ready", "failed"]:
        raise HTTPException(status_code=400, detail="ジョブが適切な状態ではありません")

    if async_worker.is_task_running(f"complete_{job_id}"):
        raise HTTPException(status_code=409, detail="このジョブは既に処理中です")

    metadata_path = Path.cwd() / "data" / job_id / "video_settings.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    video_settings = {
        "bgm_enabled": bgm_enabled,
        "bgm_path": bgm_path,
        "bgm_volume": bgm_volume,
        "transition_type": transition_type,
        "transition_duration": transition_duration,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(video_settings, f, ensure_ascii=False, indent=2)

    JobService.update_job(
        job_id=job_id,
        status="processing",
        status_code=StatusCode.PROCESSING,
        error_code=None,
        progress=5,
    )

    from api.core.job_processor import JobProcessor  # lazy: 内部で重い依存
    asyncio.create_task(JobProcessor.process_complete_video_async(job_id, jobs_db))
    return {"message": "動画生成を開始しました（非同期処理）", "job_id": job_id}


@router.post("/{job_id}/generate-video-direct")
async def generate_video_directly(job_id: str, background_tasks: BackgroundTasks):
    """スライド準備完了後、動画生成を直接実行。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs_db[job_id]
    if job.status not in ["slides_ready", "audio_ready"]:
        raise HTTPException(
            status_code=400,
            detail=f"Job must be in 'slides_ready' or 'audio_ready' state. Current: {job.status}",
        )

    job.status = "processing"
    job.status_code = StatusCode.VIDEO_CREATING
    job.updated_at = datetime.now()

    background_tasks.add_task(generate_complete_video, job_id)
    return {"message": "Video generation started", "job_id": job_id}
