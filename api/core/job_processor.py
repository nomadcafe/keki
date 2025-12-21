"""
ジョブ処理モジュール - 非同期でのデータ処理
"""
import sys
from pathlib import Path
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import logging

# プロジェクトのパスを追加
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from api.core.status_codes import StatusCode
from api.core.async_worker import async_worker
from api.database.job_service import JobService

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobProcessor:
    """ジョブ処理の非同期実装"""
    
    @staticmethod
    def process_pdf_sync(job_id: str, pdf_path: str, jobs_db: Dict[str, Any]) -> int:
        """PDF処理の同期版（ワーカーで実行される）"""
        try:
            from api.core.pdf_processor import PDFProcessor
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.PDF_PROCESSING,
                progress=10
            )
            
            processor = PDFProcessor(job_id, Path.cwd())
            slide_count = processor.convert_pdf_to_slides(pdf_path)
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status_code=StatusCode.PDF_COMPLETED,
                progress=25,
                error_code=None
            )
            
            logger.info(f"PDF処理完了: {job_id}, スライド数: {slide_count}")
            return slide_count
            
        except Exception as e:
            # データベースにエラー状態を保存
            JobService.update_job(
                job_id=job_id,
                status="failed",
                status_code=StatusCode.FAILED,
                error_code=StatusCode.PDF_PROCESSING_ERROR
            )
            logger.error(f"PDF処理エラー {job_id}: {str(e)}")
            raise
    
    @staticmethod
    def generate_dialogue_sync(job_id: str, additional_prompt: Optional[str], jobs_db: Dict[str, Any], api_key: Optional[str] = None, provider: Optional[str] = None) -> None:
        """対話生成の同期版（ワーカーで実行される）"""
        try:
            import asyncio
            from api.core.dialogue_generator import DialogueGenerator
            from api.core.text_extractor import TextExtractor
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.DIALOGUE_GENERATING,
                progress=30
            )
            
            # PDFファイルからテキストを抽出
            job_dir = Path.cwd() / "uploads" / job_id
            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            
            extractor = TextExtractor()
            slide_texts = extractor.extract_text_from_pdf(str(pdf_files[0]))
            
            # ユーザー設定の重要度を読み込み（存在する場合）
            user_importance_map = None
            data_dir = Path.cwd() / "data" / job_id
            importance_path = data_dir / "slide_importance.json"
            if importance_path.exists():
                try:
                    with open(importance_path, 'r', encoding='utf-8') as f:
                        importance_data = json.load(f)
                        # キーを整数に変換
                        user_importance_map = {int(k): float(v) for k, v in importance_data.items()}
                        logger.info(f"ユーザー設定の重要度を使用（再生成）: {user_importance_map}")
                except Exception as e:
                    logger.warning(f"重要度ファイルの読み込みエラー: {e}")
            
            # 対話生成を実行（APIキーを渡す）
            generator = DialogueGenerator(api_key=api_key, provider=provider)
            
            # 非同期関数を同期で実行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                dialogue_data = loop.run_until_complete(
                    generator.extract_text_from_slides(
                        slide_texts, 
                        additional_prompt=additional_prompt,
                        target_duration=10,  # デフォルト10分
                        user_importance_map=user_importance_map
                    )
                )
                
                # 対話データを保存
                data_dir = Path.cwd() / "data" / job_id
                data_dir.mkdir(parents=True, exist_ok=True)
                
                with open(data_dir / "dialogue_narration_original.json", "w", encoding="utf-8") as f:
                    json.dump(dialogue_data, f, ensure_ascii=False, indent=2)
                    
            finally:
                loop.close()
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status_code=StatusCode.DIALOGUE_COMPLETED,
                progress=60,
                error_code=None
            )
            
            logger.info(f"対話生成完了: {job_id}")
            
        except Exception as e:
            # データベースにエラー状態を保存
            JobService.update_job(
                job_id=job_id,
                status="failed",
                status_code=StatusCode.FAILED,
                error_code=StatusCode.DIALOGUE_GENERATION_ERROR
            )
            logger.error(f"対話生成エラー {job_id}: {str(e)}")
            raise
    
    @staticmethod
    def generate_audio_sync(job_id: str, speed_scale: float, pitch_scale: float, 
                          intonation_scale: float, volume_scale: float, jobs_db: Dict[str, Any]) -> None:
        """音声生成の同期版（ワーカーで実行される）"""
        try:
            from api.core.audio_generator import AudioGenerator
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.AUDIO_GENERATING,
                progress=65
            )
            
            generator = AudioGenerator(job_id, Path.cwd())
            generator.generate_audio_files(
                speed_scale=speed_scale,
                pitch_scale=pitch_scale,
                intonation_scale=intonation_scale,
                volume_scale=volume_scale
            )
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status_code=StatusCode.AUDIO_COMPLETED,
                progress=85,
                error_code=None
            )
            
            logger.info(f"音声生成完了: {job_id}")
            
        except Exception as e:
            # データベースにエラー状態を保存
            JobService.update_job(
                job_id=job_id,
                status="failed",
                status_code=StatusCode.FAILED,
                error_code=StatusCode.AUDIO_GENERATION_ERROR
            )
            logger.error(f"音声生成エラー {job_id}: {str(e)}")
            raise
    
    @staticmethod
    def create_video_sync(job_id: str, jobs_db: Dict[str, Any]) -> str:
        """動画作成の同期版（ワーカーで実行される）"""
        try:
            from api.core.video_creator import VideoCreator
            import json
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.VIDEO_CREATING,
                progress=90
            )
            
            # 動画設定を読み込み（存在する場合）
            video_settings_path = Path.cwd() / "data" / job_id / "video_settings.json"
            bgm_enabled = False
            bgm_path = None
            bgm_volume = 0.15
            transition_type = "crossfade"
            transition_duration = 0.4
            
            if video_settings_path.exists():
                try:
                    with open(video_settings_path, 'r', encoding='utf-8') as f:
                        video_settings = json.load(f)
                        bgm_enabled = video_settings.get("bgm_enabled", False)
                        bgm_path = video_settings.get("bgm_path")
                        bgm_volume = video_settings.get("bgm_volume", 0.15)
                        transition_type = video_settings.get("transition_type", "crossfade")
                        transition_duration = video_settings.get("transition_duration", 0.4)
                except Exception as e:
                    logger.warning(f"動画設定の読み込みエラー: {e}")
            
            logger.info(f"動画作成を開始: {job_id}")
            creator = VideoCreator(job_id, Path.cwd())
            
            # 動画作成中に進捗を更新（95%）
            JobService.update_job(
                job_id=job_id,
                status="processing",
                status_code=StatusCode.VIDEO_ENCODING,
                progress=95
            )
            logger.info(f"動画エンコーディング中: {job_id} (この処理には数分かかる場合があります)")
            
            video_path = creator.create_video(
                bgm_enabled=bgm_enabled,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                transition_type=transition_type,
                transition_duration=transition_duration
            )
            
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="completed",
                status_code=StatusCode.COMPLETED,
                progress=100,
                result_url=f"/api/jobs/{job_id}/download",
                error_code=None
            )
            
            logger.info(f"動画作成完了: {job_id}, パス: {video_path}")
            return video_path
            
        except Exception as e:
            # データベースにエラー状態を保存
            JobService.update_job(
                job_id=job_id,
                status="failed",
                status_code=StatusCode.FAILED,
                error_code=StatusCode.VIDEO_CREATION_ERROR
            )
            logger.error(f"動画作成エラー {job_id}: {str(e)}")
            raise

    @staticmethod
    async def process_complete_video_async(job_id: str, jobs_db: Dict[str, Any], 
                                         additional_prompt: Optional[str] = None) -> None:
        """完全な動画生成フローを非同期で実行"""
        try:
            # データベースに状態を保存
            JobService.update_job(
                job_id=job_id,
                status="processing"
            )
            
            # 1. PDFファイルパスを取得
            job_dir = Path.cwd() / "uploads" / job_id
            pdf_files = list(job_dir.glob("*.pdf"))
            if not pdf_files:
                raise Exception("PDFファイルが見つかりません")
            
            pdf_path = str(pdf_files[0])
            
            # 2. PDF処理（非同期）※スライドが既にある場合でも安全のため再実行
            await async_worker.submit_task(
                f"pdf_{job_id}",
                JobProcessor.process_pdf_sync,
                job_id, pdf_path, jobs_db
            )
            await async_worker.wait_for_task(f"pdf_{job_id}")
            
            # 3. 対話データはアップロード時または編集画面で既に生成済みとみなし、
            #    ここでは音声生成と動画作成のみを行う
            # 4. 音声生成（非同期）
            await async_worker.submit_task(
                f"audio_{job_id}",
                JobProcessor.generate_audio_sync,
                job_id, 1.0, 0.0, 1.2, 1.0, jobs_db
            )
            await async_worker.wait_for_task(f"audio_{job_id}")
            
            # 5. 動画作成（非同期）
            await async_worker.submit_task(
                f"video_{job_id}",
                JobProcessor.create_video_sync,
                job_id, jobs_db
            )
            await async_worker.wait_for_task(f"video_{job_id}")
            
            logger.info(f"完全動画生成完了: {job_id}")
            
        except Exception as e:
            # データベースにエラー状態を保存
            JobService.update_job(
                job_id=job_id,
                status="failed",
                status_code=StatusCode.FAILED
            )
            logger.error(f"完全動画生成エラー {job_id}: {str(e)}")
            raise