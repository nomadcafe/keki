"""jobs ルーター内部で共有するコンテキスト。"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import Dict, List, Optional

from api.database.job_service import JobService


UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

PDF_MAX_BYTES = 100 * 1024 * 1024  # 100MB
KNOWLEDGE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_PROVIDERS = {"openai", "claude", "gemini", "deepseek"}
TARGET_DURATION_RANGE = (1, 120)  # 分
SPEAKER_SPEED_RANGE = (0.5, 2.0)
SPEAKER_ID_RANGE = (0, 10000)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobsDBDict:
    """jobs_db の後方互換性ラッパー（非推奨）。

    新しいコードでは JobService を直接使用すること。
    """

    def __getitem__(self, key: str):
        job = JobService.get_job(key)
        if job:
            from api.models.job import JobStatus
            return JobStatus(**job.to_dict())
        raise KeyError(key)

    def __setitem__(self, key: str, value):
        from api.models.job import JobStatus
        if isinstance(value, JobStatus):
            JobService.update_job_from_status(value)
        elif isinstance(value, dict):
            existing_job = JobService.get_job(key)
            if existing_job:
                JobService.update_job(
                    job_id=key,
                    status=value.get("status"),
                    status_code=value.get("status_code"),
                    progress=value.get("progress"),
                    result_url=value.get("result_url"),
                    error_code=value.get("error_code"),
                    estimated_duration=value.get("estimated_duration"),
                )
            else:
                JobService.create_job(
                    job_id=key,
                    status=value.get("status", "pending"),
                    status_code=value.get("status_code", "PENDING"),
                    target_duration=value.get("target_duration"),
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
        from api.models.job import JobStatus
        return [JobStatus(**job.to_dict()) for job in JobService.list_jobs()]

    def __len__(self):
        return len(JobService.list_jobs())

    def keys(self):
        return [job.job_id for job in JobService.list_jobs()]


jobs_db = JobsDBDict()


def sanitize_filename(raw: Optional[str], field: str) -> str:
    """パストラバーサル対策を兼ねたファイル名サニタイズ。"""
    name = Path(raw or "").name
    if not name or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail=f"不正な{field}ファイル名です")
    return name


def estimate_video_duration(dialogue_data: Dict[str, List[Dict]]) -> float:
    """対話データから動画時間を概算。"""
    total_chars = 0
    total_dialogues = 0
    for dialogues in dialogue_data.values():
        for dialogue in dialogues:
            total_chars += len(dialogue.get("text", ""))
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
    return round(text_duration + slide_transition_duration + dialogue_pause_duration, 1)


def format_duration(seconds: float) -> str:
    """秒数を分:秒形式にフォーマット。"""
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"
