"""ジョブ処理のバックグラウンドパイプライン関数。

pdf_processor / audio_generator / video_creator は pdf2image, moviepy 等の
重い依存を取り込むため lazy import する（起動時の失敗を回避）。
"""
import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from api.core.status_codes import StatusCode
from api.database.job_service import JobService

from ._shared import UPLOAD_DIR, jobs_db


async def convert_pdf_to_slides(
    job_id: str,
    pdf_path: str,
    target_duration: int = 10,
    metadata: dict = None,
    api_key: str = None,
    provider: str = None,
):
    """PDFをスライド画像に変換し対話データを生成。"""
    try:
        from api.core.pdf_processor import PDFProcessor  # lazy: 重い依存

        JobService.update_job(
            job_id=job_id,
            status="processing",
            status_code=StatusCode.PDF_PROCESSING,
            progress=10,
        )

        processor = PDFProcessor(job_id, Path.cwd())
        processor.convert_pdf_to_slides(pdf_path)

        JobService.update_job(job_id=job_id, progress=15)

        def update_progress(message: str, progress: float):
            JobService.update_job(
                job_id=job_id,
                progress=15 + int(progress * 0.8),
            )

        speaker_info = None
        conversation_style_prompt = None
        additional_knowledge = None
        if metadata:
            speaker_info = {
                "speaker1": metadata.get("speaker1"),
                "speaker2": metadata.get("speaker2"),
            }
            conversation_style_prompt = metadata.get("conversation_style_prompt", "")
            additional_knowledge = metadata.get("additional_knowledge", "")

        combined_prompt = conversation_style_prompt
        if additional_knowledge:
            combined_prompt = (
                f"{combined_prompt}\n\n{additional_knowledge}"
                if combined_prompt
                else additional_knowledge
            )

        JobService.update_job(job_id=job_id, status_code=StatusCode.DIALOGUE_GENERATING)
        api_key_to_use = api_key or (metadata.get("api_key") if metadata else None)
        provider_to_use = provider or (metadata.get("provider") if metadata else None)
        await processor.generate_dialogue_from_pdf(
            pdf_path,
            additional_prompt=combined_prompt,
            progress_callback=update_progress,
            target_duration=target_duration,
            speaker_info=speaker_info,
            additional_knowledge=additional_knowledge,
            api_key=api_key_to_use,
            provider=provider_to_use,
        )

        JobService.update_job(
            job_id=job_id,
            status="slides_ready",
            status_code=StatusCode.DIALOGUE_COMPLETED,
            progress=50,
        )

    except Exception as e:
        error_msg = f"Error in convert_pdf_to_slides: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.PDF_PROCESSING_ERROR,
        )


async def generate_complete_video(job_id: str):
    """完全な動画生成フロー（全工程を自動実行）。"""
    try:
        from api.core.audio_generator import AudioGenerator  # lazy: 重い依存
        from api.core.pdf_processor import PDFProcessor
        from api.core.video_creator import VideoCreator

        job = jobs_db[job_id]

        slides_dir = Path.cwd() / "slides" / job_id
        job_dir = UPLOAD_DIR / job_id
        processor = PDFProcessor(job_id, Path.cwd())

        if not slides_dir.exists() or not list(slides_dir.glob("slide_*.png")):
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.PDF_PROCESSING,
                progress=10,
            )
            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            pdf_path = str(pdf_files[0])
            JobService.update_job(
                job_id=job_id,
                status_code=StatusCode.PDF_GENERATING_SLIDES,
                progress=15,
            )
            processor.convert_pdf_to_slides(pdf_path)
        else:
            JobService.update_job(job_id=job_id, progress=20)

        data_dir = Path.cwd() / "data" / job_id
        dialogue_path = data_dir / "dialogue_narration_original.json"

        if not dialogue_path.exists():
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.DIALOGUE_GENERATING,
                progress=25,
            )

            def update_progress(message: str, progress: float):
                status_code = (
                    StatusCode.DIALOGUE_PROCESSING
                    if "生成中" in message
                    else StatusCode.DIALOGUE_GENERATING
                )
                JobService.update_job(
                    job_id=job_id,
                    status_code=status_code,
                    progress=25 + int(progress * 0.35),
                )

            target_duration = job.target_duration or 10
            metadata_path = job_dir / "metadata.json"
            speaker_info = None
            api_key_from_metadata = None
            provider_from_metadata = None
            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    speaker_info = metadata.get("speakers", {})
                    api_key_from_metadata = metadata.get("api_key")
                    provider_from_metadata = metadata.get("provider")

            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            pdf_path = str(pdf_files[0])

            await processor.generate_dialogue_from_pdf(
                pdf_path,
                progress_callback=update_progress,
                target_duration=target_duration,
                speaker_info=speaker_info,
                api_key=api_key_from_metadata,
                provider=provider_from_metadata,
            )
        else:
            JobService.update_job(job_id=job_id, progress=60)

        JobService.update_job(
            job_id=job_id,
            status="processing",
            status_code=StatusCode.AUDIO_GENERATING,
            progress=60,
        )
        audio_generator = AudioGenerator(job_id, Path.cwd())
        audio_generator.generate_audio_files(
            speed_scale=1.0,
            pitch_scale=0.0,
            intonation_scale=1.2,
            volume_scale=1.0,
        )

        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_CREATING,
            progress=80,
        )

        video_creator = VideoCreator(job_id, Path.cwd())
        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_ENCODING,
            progress=85,
        )
        video_creator.create_video()

        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_FINALIZING,
            progress=95,
        )

        JobService.update_job(
            job_id=job_id,
            status="completed",
            status_code=StatusCode.COMPLETED,
            progress=100,
            result_url=f"/api/jobs/{job_id}/download",
            error_code=None,
        )

    except Exception as e:
        error_msg = f"Error in generate_complete_video: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.VIDEO_CREATION_ERROR,
        )


async def generate_audio_task(
    job_id: str,
    speed_scale: float,
    pitch_scale: float,
    intonation_scale: float,
    volume_scale: float,
):
    """音声を生成。"""
    try:
        from api.core.audio_generator import AudioGenerator  # lazy: 重い依存

        JobService.update_job(job_id=job_id, progress=40)
        generator = AudioGenerator(job_id, Path.cwd())
        generator.generate_audio_files(
            speed_scale=speed_scale,
            pitch_scale=pitch_scale,
            intonation_scale=intonation_scale,
            volume_scale=volume_scale,
        )
        JobService.update_job(
            job_id=job_id,
            status="audio_ready",
            status_code=StatusCode.COMPLETED,
            progress=60,
            error_code=None,
        )
    except Exception:
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.AUDIO_GENERATION_ERROR,
        )


async def create_video_task(
    job_id: str,
    slide_numbers: Optional[List[int]],
    bgm_enabled: bool = False,
    bgm_path: Optional[str] = None,
    bgm_volume: float = 0.15,
    transition_type: str = "crossfade",
    transition_duration: float = 0.4,
):
    """動画を作成。"""
    try:
        from api.core.video_creator import VideoCreator  # lazy: 重い依存

        JobService.update_job(job_id=job_id, progress=80)
        creator = VideoCreator(job_id, Path.cwd())
        creator.create_video(
            slide_numbers,
            bgm_enabled=bgm_enabled,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            transition_type=transition_type,
            transition_duration=transition_duration,
        )
        JobService.update_job(
            job_id=job_id,
            status="completed",
            status_code=StatusCode.COMPLETED,
            progress=100,
            result_url=f"/api/jobs/{job_id}/download",
            error_code=None,
        )
    except Exception as e:
        error_msg = f"Error in create_video_task: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.VIDEO_CREATION_ERROR,
        )
