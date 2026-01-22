"""
データベースモデル定義
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Job(Base):
    """ジョブテーブル"""
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    status = Column(String, nullable=False, default="pending")  # pending, processing, completed, failed
    status_code = Column(String, nullable=False, default="PENDING")  # ステータスコード
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    progress = Column(Integer, nullable=False, default=0)  # 0-100
    result_url = Column(String, nullable=True)
    error_code = Column(String, nullable=True)  # エラーコード
    estimated_duration = Column(Integer, nullable=True)  # 推定動画時間（秒）
    target_duration = Column(Integer, nullable=True)  # 目標動画時間（分）
    
    # 追加メタデータ（JSON形式で保存）
    metadata_json = Column(Text, nullable=True)  # JSON形式のメタデータ

    def to_dict(self):
        """辞書形式に変換（Pydanticモデル互換）"""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "status_code": self.status_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
            "result_url": self.result_url,
            "error_code": self.error_code,
            "estimated_duration": self.estimated_duration,
            "target_duration": self.target_duration
        }




