"""
ジョブデータベースサービス層
jobs_db グローバル変数の代替
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from api.database.models import Job
from api.database.db import get_db_session
from api.models.job import JobStatus
import json


class JobService:
    """ジョブデータベース操作サービス"""
    
    @staticmethod
    def create_job(
        job_id: str,
        status: str = "pending",
        status_code: str = "PENDING",
        target_duration: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Job:
        """新しいジョブを作成"""
        db = get_db_session()
        try:
            job = Job(
                job_id=job_id,
                status=status,
                status_code=status_code,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=0,
                target_duration=target_duration,
                metadata_json=json.dumps(metadata) if metadata else None
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job
        finally:
            db.close()
    
    @staticmethod
    def get_job(job_id: str) -> Optional[Job]:
        """ジョブを取得"""
        db = get_db_session()
        try:
            return db.query(Job).filter(Job.job_id == job_id).first()
        finally:
            db.close()
    
    @staticmethod
    def get_job_dict(job_id: str) -> Optional[Dict[str, Any]]:
        """ジョブを辞書形式で取得（Pydanticモデル互換）"""
        job = JobService.get_job(job_id)
        if job:
            return job.to_dict()
        return None
    
    @staticmethod
    def update_job(
        job_id: str,
        status: Optional[str] = None,
        status_code: Optional[str] = None,
        progress: Optional[int] = None,
        result_url: Optional[str] = None,
        error_code: Optional[str] = None,
        estimated_duration: Optional[int] = None,
        target_duration: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Job]:
        """ジョブを更新"""
        db = get_db_session()
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return None
            
            if status is not None:
                job.status = status
            if status_code is not None:
                job.status_code = status_code
            if progress is not None:
                job.progress = progress
            if result_url is not None:
                job.result_url = result_url
            if error_code is not None:
                job.error_code = error_code
            if estimated_duration is not None:
                job.estimated_duration = estimated_duration
            if target_duration is not None:
                job.target_duration = target_duration
            if metadata is not None:
                # 既存のメタデータとマージ
                existing_metadata = {}
                if job.metadata_json:
                    try:
                        existing_metadata = json.loads(job.metadata_json)
                    except:
                        pass
                existing_metadata.update(metadata)
                job.metadata_json = json.dumps(existing_metadata)
            
            job.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job
        finally:
            db.close()
    
    @staticmethod
    def update_job_from_status(job_status: 'JobStatus') -> Optional[Job]:
        """JobStatusオブジェクトからジョブを更新"""
        return JobService.update_job(
            job_id=job_status.job_id,
            status=job_status.status,
            status_code=job_status.status_code,
            progress=job_status.progress,
            result_url=job_status.result_url,
            error_code=job_status.error_code,
            estimated_duration=job_status.estimated_duration,
            target_duration=job_status.target_duration
        )
    
    @staticmethod
    def delete_job(job_id: str) -> bool:
        """ジョブを削除"""
        db = get_db_session()
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return False
            db.delete(job)
            db.commit()
            return True
        finally:
            db.close()
    
    @staticmethod
    def list_jobs(limit: Optional[int] = None, offset: int = 0, status: Optional[str] = None) -> List[Job]:
        """ジョブリストを取得（オプション: statusでフィルタ）"""
        db = get_db_session()
        try:
            query = db.query(Job).order_by(Job.created_at.desc())
            if status:
                query = query.filter(Job.status == status)
            if limit:
                query = query.limit(limit).offset(offset)
            return query.all()
        finally:
            db.close()
    
    @staticmethod
    def list_jobs_dict(limit: Optional[int] = None, offset: int = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """ジョブリストを辞書形式で取得（metadata含む）"""
        jobs = JobService.list_jobs(limit, offset, status)
        return [job.to_dict() for job in jobs]
    
    @staticmethod
    def get_job_status(job_id: str) -> Optional[JobStatus]:
        """ジョブステータスをPydanticモデルで取得"""
        job = JobService.get_job(job_id)
        if job:
            return JobStatus(**job.to_dict())
        return None
    
    @staticmethod
    def job_exists(job_id: str) -> bool:
        """ジョブが存在するかチェック"""
        return JobService.get_job(job_id) is not None

