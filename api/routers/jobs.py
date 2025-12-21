"""
ジョブ関連のルート
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse
from fastapi import Form
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path
import shutil
import json
import csv
import io
import uuid
import asyncio
import threading

from api.models.job import (
    JobStatus, JobCreateResponse, GenerateAudioRequest, 
    CreateVideoRequest, GenerateDialogueRequest, UpdateDialogueRequest,
    SlideImportanceRequest
)
from api.core.status_codes import StatusCode
from api.core.job_processor import JobProcessor
from api.core.async_worker import async_worker
from api.core.knowledge_extractor import extract_text_from_knowledge_file

# データベースサービスをインポート
from api.database.job_service import JobService

# 後方互換性のため、jobs_db を辞書としてアクセス可能にする（非推奨）
# 新しいコードでは JobService を使用すること
class JobsDBDict:
    """jobs_db の後方互換性ラッパー（非推奨）"""
    def __getitem__(self, key: str):
        job = JobService.get_job(key)
        if job:
            # JobStatus オブジェクトを返す（既存コードとの互換性）
            from api.models.job import JobStatus
            return JobStatus(**job.to_dict())
        raise KeyError(key)
    
    def __setitem__(self, key: str, value):
        # JobStatus オブジェクトから Job を作成または更新
        from api.models.job import JobStatus
        if isinstance(value, JobStatus):
            # 既存のジョブを更新
            JobService.update_job_from_status(value)
        elif isinstance(value, dict):
            # 辞書の場合、既存のジョブを更新または新規作成
            existing_job = JobService.get_job(key)
            if existing_job:
                JobService.update_job(
                    job_id=key,
                    status=value.get("status"),
                    status_code=value.get("status_code"),
                    progress=value.get("progress"),
                    result_url=value.get("result_url"),
                    error_code=value.get("error_code"),
                    estimated_duration=value.get("estimated_duration")
                )
            else:
                JobService.create_job(
                    job_id=key,
                    status=value.get("status", "pending"),
                    status_code=value.get("status_code", "PENDING"),
                    target_duration=value.get("target_duration")
                )
    
    def __delitem__(self, key: str):
        JobService.delete_job(key)
    
    def __contains__(self, key: str) -> bool:
        return JobService.job_exists(key)
    
    def get(self, key: str, default=None):
        job = JobService.get_job(key)
        if job:
            from api.models.job import JobStatus
            return JobStatus(**job.to_dict())
        return default
    
    def values(self):
        jobs = JobService.list_jobs()
        from api.models.job import JobStatus
        return [JobStatus(**job.to_dict()) for job in jobs]
    
    def __len__(self):
        return len(JobService.list_jobs())
    
    def keys(self):
        jobs = JobService.list_jobs()
        return [job.job_id for job in jobs]

jobs_db = JobsDBDict()  # 後方互換性のため
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/upload", response_model=JobCreateResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_duration: int = Form(10),  # デフォルト10分
    speaker1_id: int = Form(2),
    speaker1_name: str = Form("四国めたん"),
    speaker1_speed: float = Form(1.0),
    speaker2_id: int = Form(3),
    speaker2_name: str = Form("ずんだもん"),
    speaker2_speed: float = Form(1.0),
    conversation_style: str = Form("friendly"),
    conversation_style_prompt: str = Form(""),
    knowledge_file: UploadFile = File(None),  # ナレッジファイル
    api_key: Optional[str] = Form(None),  # APIキー（オプション）
    provider: Optional[str] = Form(None)  # プロバイダー（オプション）
):
    """PDFファイルをアップロードしてジョブを作成"""
    
    # ファイル名のサニタイズ（パストラバーサル対策）
    original_pdf_filename = file.filename or ""
    safe_pdf_name = Path(original_pdf_filename).name  # パス要素を除去
    if ".." in safe_pdf_name or "/" in safe_pdf_name or "\\" in safe_pdf_name:
        raise HTTPException(status_code=400, detail="不正なファイル名です")

    # ファイル検証（拡張子）
    if not safe_pdf_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルのみ対応しています")
    
    # ファイルサイズ検証（100MB）
    if file.size and file.size > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ファイルサイズが大きすぎます（最大100MB）")
    
    # ジョブID生成
    job_id = str(uuid.uuid4())
    
    # ファイル保存（本番ではS3に保存）
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    pdf_path = job_dir / safe_pdf_name
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # ナレッジファイルの処理
    knowledge_text = ""
    if knowledge_file and knowledge_file.filename:
        # ナレッジファイルのファイル名をサニタイズ
        original_knowledge_filename = knowledge_file.filename
        safe_knowledge_name = Path(original_knowledge_filename).name
        if ".." in safe_knowledge_name or "/" in safe_knowledge_name or "\\" in safe_knowledge_name:
            raise HTTPException(status_code=400, detail="不正なナレッジファイル名です")

        # ナレッジファイルを保存
        knowledge_path = job_dir / safe_knowledge_name
        with open(knowledge_path, "wb") as buffer:
            shutil.copyfileobj(knowledge_file.file, buffer)
        
        # ナレッジファイルからテキストを抽出
        try:
            knowledge_text = extract_text_from_knowledge_file(str(knowledge_path))
        except Exception as e:
            print(f"ナレッジファイルの処理エラー: {e}")
            knowledge_text = ""
    
    # ジョブ情報をデータベースに保存
    metadata = {
        "target_duration": target_duration,
        "speaker1": {"id": speaker1_id, "name": speaker1_name, "speed": speaker1_speed},
        "speaker2": {"id": speaker2_id, "name": speaker2_name, "speed": speaker2_speed},
        "conversation_style": conversation_style,
        "conversation_style_prompt": conversation_style_prompt,
        "additional_knowledge": knowledge_text,
        "api_key": api_key,  # APIキーをメタデータに保存
        "provider": provider  # プロバイダーをメタデータに保存
    }
    
    JobService.create_job(
        job_id=job_id,
        status="pending",
        status_code=StatusCode.PDF_UPLOADING,
        target_duration=target_duration,
        metadata=metadata
    )
    
    # 後方互換性のため、jobs_db にも設定（非推奨）
    job_status = JobStatus(
        job_id=job_id,
        status="pending",
        status_code=StatusCode.PDF_UPLOADING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        progress=0,
        target_duration=target_duration
    )
    
    # メタデータをファイルにも保存（後方互換性のため）
    metadata_file = job_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    # 目安時間をファイルに保存（後方互換性のため）
    target_duration_file = job_dir / "target_duration.txt"
    with open(target_duration_file, "w") as f:
        f.write(str(target_duration))
    
    # バックグラウンドでPDF変換を実行（本番ではBatchジョブ起動）
    def run_in_thread():
        asyncio.run(convert_pdf_to_slides(job_id, str(pdf_path), target_duration, metadata, api_key, provider))
    
    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True
    thread.start()
    
    return JobCreateResponse(job_id=job_id)


@router.get("/{job_id}/status", response_model=JobStatus)
async def get_job_status(job_id: str):
    """ジョブのステータスを取得"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return jobs_db[job_id]


@router.get("", response_model=List[JobStatus])
async def list_jobs():
    """全ジョブのリストを取得"""
    return list(jobs_db.values())


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """ジョブを削除"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # ファイル削除（本番ではS3から削除）
    job_dir = UPLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    
    output_file = OUTPUT_DIR / f"{job_id}.mp4"
    if output_file.exists():
        output_file.unlink()
    
    # ジョブ情報削除
    del jobs_db[job_id]
    
    return {"message": "ジョブを削除しました"}


# バックグラウンドタスク関数（main.pyから移動予定）
async def convert_pdf_to_slides(
    job_id: str,
    pdf_path: str,
    target_duration: int = 10,
    metadata: dict = None,
    api_key: str = None,
    provider: str = None,
):
    """PDFをスライド画像に変換"""
    try:
        # ここでの import 失敗もジョブ失敗として扱う（ステータスがずっと pending にならないように）
        from api.core.pdf_processor import PDFProcessor  # type: ignore
    except Exception as e:
        import traceback

        error_msg = f"PDFProcessor import error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        # データベースにエラー状態を保存
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.PDF_PROCESSING_ERROR
        )
        return

    try:
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status="processing",
            status_code=StatusCode.PDF_PROCESSING,
            progress=10
        )

        # PDFをスライドに変換
        processor = PDFProcessor(job_id, Path.cwd())
        slide_count = processor.convert_pdf_to_slides(pdf_path)

        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            progress=15
        )

        # 進捗更新用のコールバック
        def update_progress(message: str, progress: float):
            JobService.update_job(
                job_id=job_id,
                progress=15 + int(progress * 0.8)
            )

        # メタデータがある場合はスピーカー情報と会話スタイル、ナレッジを取得
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

        # プロンプトを結合
        combined_prompt = conversation_style_prompt
        if additional_knowledge:
            if combined_prompt:
                combined_prompt = f"{combined_prompt}\n\n{additional_knowledge}"
            else:
                combined_prompt = additional_knowledge

        # 対話データを生成（APIキーを渡す）
        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.DIALOGUE_GENERATING
        )
        # メタデータからAPIキーとプロバイダーを取得
        api_key_to_use = api_key or (metadata.get("api_key") if metadata else None)
        provider_to_use = provider or (metadata.get("provider") if metadata else None)
        dialogue_path = await processor.generate_dialogue_from_pdf(
            pdf_path,
            additional_prompt=combined_prompt,
            progress_callback=update_progress,
            target_duration=target_duration,
            speaker_info=speaker_info,
            additional_knowledge=additional_knowledge,
            api_key=api_key_to_use,
            provider=provider_to_use,
        )

        # スライドと対話スクリプトの準備完了
        JobService.update_job(
            job_id=job_id,
            status="slides_ready",
            status_code=StatusCode.DIALOGUE_COMPLETED,
            progress=50
        )

    except Exception as e:
        import traceback

        error_msg = f"Error in convert_pdf_to_slides: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        # データベースにエラー状態を保存
        JobService.update_job(
            job_id=job_id,
            status="failed",
            status_code=StatusCode.FAILED,
            error_code=StatusCode.PDF_PROCESSING_ERROR
        )


async def generate_complete_video(job_id: str):
    """完全な動画生成フロー（全工程を自動実行）"""
    from api.core.pdf_processor import PDFProcessor
    from api.core.audio_generator import AudioGenerator
    from api.core.video_creator import VideoCreator
    
    try:
        job = jobs_db[job_id]
        
        # 1. PDFをスライドに変換（必要な場合のみ）
        slides_dir = Path.cwd() / "slides" / job_id
        job_dir = UPLOAD_DIR / job_id
        processor = PDFProcessor(job_id, Path.cwd())
        
        if not slides_dir.exists() or not list(slides_dir.glob("slide_*.png")):
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.PDF_PROCESSING,
                progress=10
            )
            
            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            
            pdf_path = str(pdf_files[0])
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status_code=StatusCode.PDF_GENERATING_SLIDES,
                progress=15
            )
            
            slide_count = processor.convert_pdf_to_slides(pdf_path)
        else:
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                progress=20
            )
            slide_count = len(list(slides_dir.glob("slide_*.png")))
        
        # 2. 対話データの確認・生成
        data_dir = Path.cwd() / "data" / job_id
        dialogue_path = data_dir / "dialogue_narration_original.json"
        
        if not dialogue_path.exists():
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.DIALOGUE_GENERATING,
                progress=25
            )
            
            def update_progress(message: str, progress: float):
                status_code = StatusCode.DIALOGUE_PROCESSING if "生成中" in message else StatusCode.DIALOGUE_GENERATING
                JobService.update_job(
                    job_id=job_id,
                    status_code=status_code,
                    progress=25 + int(progress * 0.35)
                )
            
            target_duration = job.target_duration or 10
            metadata_path = job_dir / "metadata.json"
            metadata = None
            speaker_info = None
            api_key_from_metadata = None
            provider_from_metadata = None
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    speaker_info = metadata.get('speakers', {})
                    api_key_from_metadata = metadata.get('api_key')
                    provider_from_metadata = metadata.get('provider')
            
            # PDFファイルパスを取得
            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            pdf_path = str(pdf_files[0])
            
            dialogue_path = await processor.generate_dialogue_from_pdf(
                pdf_path, 
                progress_callback=update_progress,
                target_duration=target_duration,
                speaker_info=speaker_info,
                api_key=api_key_from_metadata,
                provider=provider_from_metadata
            )
        else:
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                progress=60
            )
        
        # 3. 音声生成
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status="processing",
            status_code=StatusCode.AUDIO_GENERATING,
            progress=60
        )
        
        audio_generator = AudioGenerator(job_id, Path.cwd())
        audio_count = audio_generator.generate_audio_files(
            speed_scale=1.0,
            pitch_scale=0.0,
            intonation_scale=1.2,
            volume_scale=1.0
        )
        
        # 4. 動画作成
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_CREATING,
            progress=80
        )
        
        video_creator = VideoCreator(job_id, Path.cwd())
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_ENCODING,
            progress=85
        )
        
        video_path = video_creator.create_video()
        
        # 動画ファイナライズ
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status_code=StatusCode.VIDEO_FINALIZING,
            progress=95
        )
        
        # 5. 完了
        # データベースに状態を保存
        JobService.update_job(
            job_id=job_id,
            status="completed",
            status_code=StatusCode.COMPLETED,
            progress=100,
            result_url=f"/api/jobs/{job_id}/download"
        )
        job.error_code = None
        job.updated_at = datetime.now()
        
    except Exception as e:
        import traceback
        error_msg = f"Error in generate_complete_video: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        job = jobs_db[job_id]
        job.status = "failed"
        job.status_code = StatusCode.FAILED
        job.error_code = StatusCode.VIDEO_CREATION_ERROR
        job.updated_at = datetime.now()


# 動画時間の概算関数
def estimate_video_duration(dialogue_data: Dict[str, List[Dict]]) -> float:
    """対話データから動画時間を概算"""
    total_chars = 0
    total_dialogues = 0
    
    for slide_key, dialogues in dialogue_data.items():
        for dialogue in dialogues:
            text = dialogue.get("text", "")
            total_chars += len(text)
            total_dialogues += 1
    
    # 概算:
    # - 日本語の読み上げ速度: 約300-350文字/分（VOICEVOXのデフォルト速度）
    # - スライド間の間隔: 0.5秒 × スライド数
    # - 対話間の間隔: 0.3秒 × 対話数
    
    chars_per_second = 5.5  # 330文字/分 ÷ 60秒
    text_duration = total_chars / chars_per_second
    
    slide_count = len(dialogue_data)
    slide_transition_duration = slide_count * 0.5
    dialogue_pause_duration = total_dialogues * 0.3
    
    total_seconds = text_duration + slide_transition_duration + dialogue_pause_duration
    
    return round(total_seconds, 1)


def format_duration(seconds: float) -> str:
    """秒数を分:秒形式にフォーマット"""
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"


@router.post("/{job_id}/generate-audio")
async def generate_audio(
    job_id: str,
    request: GenerateAudioRequest,
    background_tasks: BackgroundTasks
):
    """音声生成を開始"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    job = jobs_db[job_id]
    
    if job.status not in ["slides_ready", "dialogue_ready"]:
        raise HTTPException(
            status_code=400, 
            detail="スライド変換または対話スクリプトの準備が完了していません"
        )
    
    # ステータス更新
    job.status = "generating_audio"
    job.status_code = StatusCode.AUDIO_GENERATING
    job.progress = 30
    job.updated_at = datetime.now()
    
    # バックグラウンドで音声生成
    background_tasks.add_task(
        generate_audio_task, 
        job_id,
        request.speed_scale,
        request.pitch_scale,
        request.intonation_scale,
        request.volume_scale
    )
    
    return {"message": "音声生成を開始しました"}


@router.post("/{job_id}/create-video")
async def create_video(
    job_id: str,
    request: CreateVideoRequest,
    background_tasks: BackgroundTasks
):
    """動画作成を開始"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    job = jobs_db[job_id]
    
    if job.status != "audio_ready":
        raise HTTPException(
            status_code=400, 
            detail="音声生成が完了していません"
        )
    
    # ステータス更新
    job.status = "creating_video"
    job.status_code = StatusCode.VIDEO_CREATING
    job.progress = 70
    job.updated_at = datetime.now()
    
    # バックグラウンドで動画作成
    background_tasks.add_task(
        create_video_task,
        job_id,
        request.slide_numbers,
        request.bgm_enabled,
        request.bgm_path,
        request.bgm_volume,
        request.transition_type,
        request.transition_duration
    )
    
    return {"message": "動画作成を開始しました"}


@router.get("/{job_id}/download")
async def download_video(job_id: str):
    """完成した動画をダウンロード"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    job = jobs_db[job_id]
    
    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="動画が完成していません"
        )
    
    video_path = OUTPUT_DIR / f"{job_id}.mp4"
    
    if not video_path.exists():
        raise HTTPException(
            status_code=404,
            detail="動画ファイルが見つかりません"
        )
    
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"video_{job_id}.mp4"
    )


@router.post("/{job_id}/generate-dialogue")
async def generate_dialogue_only(
    job_id: str,
    request: GenerateDialogueRequest,
    background_tasks: BackgroundTasks
):
    """対話スクリプトのみを生成（動画は作成しない）"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    job = jobs_db[job_id]
    
    if job.status not in ["slides_ready", "dialogue_ready", "completed"]:
        if job.status == "generating_dialogue":
            print(f"エラー: 対話生成が進行中です。ジョブID: {job_id}, ステータス: {job.status}")
            raise HTTPException(
                status_code=400, 
                detail="対話生成が進行中です。完了までお待ちください。"
            )
        elif job.status == "failed":
            print(f"エラー: 前回の処理が失敗しています。ジョブID: {job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"前回の処理が失敗しています"
            )
        else:
            print(f"エラー: 対話生成できない状態です。ジョブID: {job_id}, ステータス: {job.status}")
            raise HTTPException(
                status_code=400, 
                detail=f"対話生成できない状態です: {job.status}"
            )
    
    # 再生成の場合はタスクIDにタイムスタンプを付けて重複を避ける
    import time
    if request.additional_prompt:
        task_id = f"dialogue_regen_{job_id}_{int(time.time())}"
    else:
        task_id = f"dialogue_{job_id}"
    
    # 既に同じジョブが実行中かチェック（初回生成の場合のみ）
    if not request.additional_prompt and async_worker.is_task_running(task_id):
        raise HTTPException(
            status_code=409, 
            detail="対話生成が既に実行中です"
        )
    
    # ステータス更新
    job.status = "generating_dialogue"
    job.status_code = StatusCode.DIALOGUE_GENERATING
    job.progress = 30
    job.updated_at = datetime.now()
    
    # 非同期ワーカーで対話生成（APIキーとプロバイダーを渡す）
    await async_worker.submit_task(
        task_id,
        JobProcessor.generate_dialogue_sync,
        job_id, request.additional_prompt, jobs_db, request.api_key, request.provider
    )
    
    return {"message": "対話スクリプト生成を開始しました（非同期処理）", "job_id": job_id}


@router.get("/{job_id}/slides")
async def get_slides(job_id: str):
    """スライド画像のリストを取得"""
    slides_dir = Path.cwd() / "slides" / job_id
    
    if not slides_dir.exists():
        raise HTTPException(status_code=404, detail="スライドが見つかりません")
    
    slides = []
    for slide_path in sorted(slides_dir.glob("slide_*.png")):
        slide_num = int(slide_path.stem.split("_")[1])
        slides.append({
            "slide_number": slide_num,
            "url": f"/api/jobs/{job_id}/slides/{slide_num}"
        })
    
    return slides


@router.get("/{job_id}/slides/{slide_number}")
async def get_slide_image(job_id: str, slide_number: int):
    """特定のスライド画像を取得"""
    slide_path = Path.cwd() / "slides" / job_id / f"slide_{slide_number:03d}.png"
    
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="スライド画像が見つかりません")
    
    return FileResponse(
        path=slide_path,
        media_type="image/png"
    )


@router.get("/{job_id}/dialogue")
async def get_dialogue(job_id: str):
    """生成された対話スクリプトを取得"""
    # 今後はオリジナルデータに直接カタカナが含まれるため、オリジナルを読み込む
    dialogue_path = Path.cwd() / "data" / job_id / "dialogue_narration_original.json"
    
    if not dialogue_path.exists():
        raise HTTPException(status_code=404, detail="対話スクリプトが見つかりません")
    
    with open(dialogue_path, 'r', encoding='utf-8') as f:
        dialogue_data = json.load(f)
    
    # 動画時間の概算を計算
    total_seconds = estimate_video_duration(dialogue_data)
    
    return {
        "dialogue_data": dialogue_data,
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds)
        }
    }


@router.get("/{job_id}/metadata")
async def get_job_metadata(job_id: str):
    """ジョブのメタデータを取得"""
    metadata_path = UPLOAD_DIR / job_id / "metadata.json"
    
    if not metadata_path.exists():
        # デフォルト値を返す
        return {
            "speaker1": {"id": 2, "name": "四国めたん"},
            "speaker2": {"id": 3, "name": "ずんだもん"},
            "target_duration": 10
        }
    
    with open(metadata_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@router.get("/{job_id}/instruction-history")
async def get_instruction_history(job_id: str):
    """指示履歴を取得"""
    from api.core.instruction_history import InstructionHistory
    
    history = InstructionHistory(job_id, Path.cwd())
    return {"history": history.history}


@router.get("/{job_id}/dialogue/csv")
async def download_dialogue_csv(job_id: str):
    """対話スクリプトをCSV形式でダウンロード"""
    dialogue_path = Path.cwd() / "data" / job_id / "dialogue_narration_original.json"
    
    if not dialogue_path.exists():
        raise HTTPException(status_code=404, detail="対話スクリプトが見つかりません")
    
    with open(dialogue_path, 'r', encoding='utf-8') as f:
        dialogue_data = json.load(f)
    
    # CSV作成
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)
    
    # ヘッダー
    csv_writer.writerow(['会話番号', 'スライド番号', '発話者名', 'テキスト'])
    
    # データ
    conversation_num = 0
    for slide_key in sorted(dialogue_data.keys(), key=lambda x: int(x.split('_')[1])):
        slide_num = slide_key.split('_')[1]
        dialogues = dialogue_data[slide_key]
        
        for dialogue in dialogues:
            conversation_num += 1
            # メタデータから現在のキャラクター設定を取得
            metadata_path = Path.cwd() / "uploads" / job_id / "metadata.json"
            speaker1_name = "四国めたん"
            speaker2_name = "ずんだもん"
            
            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    speaker1_name = metadata.get("speaker1", {}).get("name", "四国めたん")
                    speaker2_name = metadata.get("speaker2", {}).get("name", "ずんだもん")
            
            # speaker1/speaker2形式の場合と、古いmetan/zundamon形式の両方に対応
            if dialogue['speaker'] == 'speaker1' or dialogue['speaker'] == 'metan':
                speaker_display = speaker1_name
            elif dialogue['speaker'] == 'speaker2' or dialogue['speaker'] == 'zundamon':
                speaker_display = speaker2_name
            else:
                speaker_display = dialogue['speaker']  # フォールバック
            csv_writer.writerow([
                conversation_num,
                slide_num,
                speaker_display,
                dialogue['text']
            ])
    
    # CSVをバイトに変換
    csv_content = csv_buffer.getvalue().encode('utf-8-sig')  # BOM付きUTF-8
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=dialogue_{job_id}.csv"
        }
    )


@router.post("/{job_id}/dialogue/csv")
async def upload_dialogue_csv(
    job_id: str,
    file: UploadFile = File(...)
):
    """CSVファイルから対話スクリプトをアップロード"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # ファイル検証
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="CSVファイルのみ対応しています")
    
    # CSVを読み込む
    content = await file.read()
    
    # エンコーディングを検出して読み込み
    try:
        csv_text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            csv_text = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_text = content.decode('shift-jis')
            except UnicodeDecodeError:
                try:
                    csv_text = content.decode('cp932')
                except UnicodeDecodeError:
                    raise HTTPException(status_code=400, detail="CSVファイルのエンコーディングが不正です（UTF-8、Shift-JIS、またはCP932を使用してください）")
    
    # CSVをパース
    csv_reader = csv.DictReader(io.StringIO(csv_text))
    
    # データを検証して読み込み
    dialogue_data = {}
    errors = []
    
    for line_num, row in enumerate(csv_reader, start=2):
        required_columns = ['会話番号', 'スライド番号', '発話者名', 'テキスト']
        missing_columns = [col for col in required_columns if col not in row]
        if missing_columns:
            errors.append(f"行{line_num}: 必要な列がありません: {', '.join(missing_columns)}")
            continue
        
        conversation_num = row.get('会話番号', '').strip()
        slide_num = row.get('スライド番号', '').strip()
        speaker_display = row.get('発話者名', '').strip()
        text = row.get('テキスト', '').strip()
        
        # 会話番号の検証
        try:
            conversation_num_int = int(conversation_num)
            if conversation_num_int < 1:
                errors.append(f"行{line_num}: 会話番号は1以上である必要があります")
                continue
        except ValueError:
            errors.append(f"行{line_num}: 会話番号が数値ではありません: {conversation_num}")
            continue
        
        # スライド番号の検証
        try:
            slide_num_int = int(slide_num)
            if slide_num_int < 1:
                errors.append(f"行{line_num}: スライド番号は1以上である必要があります")
                continue
        except ValueError:
            errors.append(f"行{line_num}: スライド番号が数値ではありません: {slide_num}")
            continue
        
        # 話者の検証と変換
        metadata_path = UPLOAD_DIR / job_id / "metadata.json"
        speaker1_name = "四国めたん"
        speaker2_name = "ずんだもん"
        
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                speaker1_name = metadata.get("speaker1", {}).get("name", "四国めたん")
                speaker2_name = metadata.get("speaker2", {}).get("name", "ずんだもん")
        
        # 話者名の判定を柔軟にする
        if speaker1_name in speaker_display.strip() or speaker_display.strip() in speaker1_name:
            speaker = 'speaker1'
        elif speaker2_name in speaker_display.strip() or speaker_display.strip() in speaker2_name:
            speaker = 'speaker2'
        elif speaker_display.strip().lower() in ['speaker1', 'キャラ1', 'キャラクター1']:
            speaker = 'speaker1'
        elif speaker_display.strip().lower() in ['speaker2', 'キャラ2', 'キャラクター2']:
            speaker = 'speaker2'
        else:
            errors.append(f"行{line_num}: 発話者名が不正です（'{speaker1_name}'または'{speaker2_name}'である必要があります）: '{speaker_display}'")
            continue
        
        # テキストの検証
        if not text.strip():
            errors.append(f"行{line_num}: テキストが空です")
            continue
        
        # スライドキーを生成
        slide_key = f"slide_{slide_num_int}"
        
        # データを追加
        if slide_key not in dialogue_data:
            dialogue_data[slide_key] = []
        
        dialogue_data[slide_key].append({
            "speaker": speaker,
            "text": text.strip()
        })
    
    # エラーがある場合は返す
    if errors:
        error_message = "CSVファイルに以下のエラーがあります:\n" + "\n".join(errors[:10])
        if len(errors) > 10:
            error_message += f"\n... 他{len(errors)-10}個のエラー"
        raise HTTPException(status_code=400, detail=error_message)
    
    # 対話データがない場合
    if not dialogue_data:
        raise HTTPException(status_code=400, detail="有効な対話データが含まれていません")
    
    # データを保存
    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)
    
    dialogue_path = data_dir / "dialogue_narration_original.json"
    with open(dialogue_path, 'w', encoding='utf-8') as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)
    
    # 互換性のためkatakanaファイルも同じ内容で保存
    katakana_path = data_dir / "dialogue_narration_katakana.json"
    with open(katakana_path, 'w', encoding='utf-8') as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)
    
    # 既存の音声ファイルを削除（新しいスクリプトで再生成が必要）
    audio_dir = Path.cwd() / "audio" / job_id
    if audio_dir.exists():
        shutil.rmtree(audio_dir)
        print(f"既存の音声ファイルを削除しました: {audio_dir}")
    
    # ジョブステータスを更新
    job = jobs_db[job_id]
    job.status = "dialogue_ready"
    job.status_code = StatusCode.DIALOGUE_COMPLETED
    job.updated_at = datetime.now()
    
    # 推定時間を再計算
    total_seconds = estimate_video_duration(dialogue_data)
    
    return {
        "message": f"対話スクリプトをインポートしました（{len(dialogue_data)}スライド）", 
        "slide_count": len(dialogue_data),
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds)
        }
    }


@router.put("/{job_id}/dialogue")
async def update_dialogue(
    job_id: str,
    request: UpdateDialogueRequest
):
    """対話スクリプトを更新"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # 対話データを保存
    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)
    
    dialogue_path = data_dir / "dialogue_narration_original.json"
    katakana_path = data_dir / "dialogue_narration_katakana.json"
    
    # 受け取ったデータをそのまま保存
    with open(dialogue_path, 'w', encoding='utf-8') as f:
        json.dump(request.dialogue_data, f, ensure_ascii=False, indent=2)
    
    # 互換性のためkatakanaファイルも同じ内容で保存
    with open(katakana_path, 'w', encoding='utf-8') as f:
        json.dump(request.dialogue_data, f, ensure_ascii=False, indent=2)
    
    # 既存の音声ファイルを削除（新しいスクリプトで再生成が必要）
    audio_dir = Path.cwd() / "audio" / job_id
    if audio_dir.exists():
        shutil.rmtree(audio_dir)
        print(f"既存の音声ファイルを削除しました: {audio_dir}")
    
    # ジョブステータスを更新
    job = jobs_db[job_id]
    job.status = "dialogue_ready"
    job.status_code = StatusCode.DIALOGUE_COMPLETED
    job.updated_at = datetime.now()
    
    # 推定時間を再計算
    total_seconds = estimate_video_duration(request.dialogue_data)
    
    return {
        "message": "対話スクリプトを更新しました",
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds)
        }
    }


@router.put("/{job_id}/slide-importance")
async def update_slide_importance(
    job_id: str,
    request: SlideImportanceRequest
):
    """スライド重要度を設定"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # 重要度マップを保存
    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)
    
    importance_path = data_dir / "slide_importance.json"
    
    # 重要度を検証（0.5-1.5の範囲）
    validated_importance = {}
    for slide_num, importance in request.importance_map.items():
        if 0.5 <= importance <= 1.5:
            validated_importance[slide_num] = importance
        else:
            raise HTTPException(
                status_code=400,
                detail=f"スライド{slide_num}の重要度は0.5〜1.5の範囲で指定してください"
            )
    
    # 重要度を保存
    with open(importance_path, 'w', encoding='utf-8') as f:
        json.dump(validated_importance, f, ensure_ascii=False, indent=2)
    
    return {
        "message": "スライド重要度を更新しました",
        "importance_map": validated_importance
    }


@router.get("/{job_id}/slide-importance")
async def get_slide_importance(job_id: str):
    """スライド重要度を取得"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    # 重要度ファイルを読み込み
    data_dir = Path.cwd() / "data" / job_id
    importance_path = data_dir / "slide_importance.json"
    
    if importance_path.exists():
        with open(importance_path, 'r', encoding='utf-8') as f:
            importance_map = json.load(f)
            # キーを整数に変換
            return {int(k): float(v) for k, v in importance_map.items()}
    else:
        # デフォルト値（すべて1.0）
        return {}


@router.post("/{job_id}/generate-video")
async def generate_video_complete(
    job_id: str,
    background_tasks: BackgroundTasks,
    bgm_enabled: bool = Form(False),
    bgm_path: Optional[str] = Form(None),
    bgm_volume: float = Form(0.15),
    transition_type: str = Form("crossfade"),
    transition_duration: float = Form(0.4)
):
    """ワンクリック動画生成（全工程を自動実行・非同期処理）"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    job = jobs_db[job_id]
    
    # 失敗状態からの再試行も許可する（ジョブ自体が存在していればOK）
    if job.status not in ["pending", "slides_ready", "dialogue_ready", "failed"]:
        raise HTTPException(
            status_code=400, 
            detail="ジョブが適切な状態ではありません"
        )
    
    # 既に同じジョブが実行中かチェック
    if async_worker.is_task_running(f"complete_{job_id}"):
        raise HTTPException(
            status_code=409, 
            detail="このジョブは既に処理中です"
        )
    
    # BGMと転場設定をメタデータに保存
    metadata_path = Path.cwd() / "data" / job_id / "video_settings.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    video_settings = {
        "bgm_enabled": bgm_enabled,
        "bgm_path": bgm_path,
        "bgm_volume": bgm_volume,
        "transition_type": transition_type,
        "transition_duration": transition_duration
    }
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(video_settings, f, ensure_ascii=False, indent=2)
    
    # ステータス更新（エラー状態をリセットして再試行を開始）
    # データベースに状態を保存
    JobService.update_job(
        job_id=job_id,
        status="processing",
        status_code=StatusCode.PROCESSING,
        error_code=None,
        progress=5
    )
    
    # 非同期で全工程を実行
    asyncio.create_task(JobProcessor.process_complete_video_async(job_id, jobs_db))
    
    return {"message": "動画生成を開始しました（非同期処理）", "job_id": job_id}


@router.post("/{job_id}/generate-video-direct")
async def generate_video_directly(job_id: str, background_tasks: BackgroundTasks):
    """スライド準備完了後、動画生成を直接実行"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_db[job_id]
    
    # ジョブが適切な状態であることを確認
    if job.status not in ["slides_ready", "audio_ready"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Job must be in 'slides_ready' or 'audio_ready' state. Current: {job.status}"
        )
    
    # 動画生成タスクを開始
    job.status = "processing"
    job.status_code = StatusCode.VIDEO_CREATING
    job.updated_at = datetime.now()
    
    background_tasks.add_task(generate_complete_video, job_id)
    
    return {"message": "Video generation started", "job_id": job_id}


# バックグラウンドタスク関数
async def generate_audio_task(
    job_id: str,
    speed_scale: float,
    pitch_scale: float,
    intonation_scale: float,
    volume_scale: float
):
    """音声を生成"""
    from api.core.audio_generator import AudioGenerator
    
    try:
        job = jobs_db[job_id]
        job.progress = 40
        
        # 音声生成
        generator = AudioGenerator(job_id, Path.cwd())
        audio_count = generator.generate_audio_files(
            speed_scale=speed_scale,
            pitch_scale=pitch_scale,
            intonation_scale=intonation_scale,
            volume_scale=volume_scale
        )
        
        job.status = "audio_ready"
        job.status_code = StatusCode.COMPLETED
        job.progress = 60
        job.error_code = None
        job.updated_at = datetime.now()
        
    except Exception as e:
        job = jobs_db[job_id]
        job.status = "failed"
        job.status_code = StatusCode.FAILED
        job.error_code = StatusCode.AUDIO_GENERATION_ERROR
        job.updated_at = datetime.now()


async def create_video_task(
    job_id: str, 
    slide_numbers: Optional[List[int]],
    bgm_enabled: bool = False,
    bgm_path: Optional[str] = None,
    bgm_volume: float = 0.15,
    transition_type: str = "crossfade",
    transition_duration: float = 0.4
):
    """動画を作成"""
    from api.core.video_creator import VideoCreator
    
    try:
        job = jobs_db[job_id]
        job.progress = 80
        
        # 動画作成
        creator = VideoCreator(job_id, Path.cwd())
        video_path = creator.create_video(
            slide_numbers,
            bgm_enabled=bgm_enabled,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            transition_type=transition_type,
            transition_duration=transition_duration
        )
        
        job.status = "completed"
        job.status_code = StatusCode.COMPLETED
        job.progress = 100
        job.result_url = f"/api/jobs/{job_id}/download"
        job.error_code = None
        job.updated_at = datetime.now()
        
    except Exception as e:
        import traceback
        error_msg = f"Error in create_video_task: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        job = jobs_db[job_id]
        job.status = "failed"
        job.status_code = StatusCode.FAILED
        job.error_code = StatusCode.VIDEO_CREATION_ERROR
        job.updated_at = datetime.now()

