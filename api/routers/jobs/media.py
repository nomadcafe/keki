"""音声・動画のメディア配信ルート。"""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ._shared import OUTPUT_DIR, jobs_db, router


@router.get("/{job_id}/audio/{filename:path}")
async def get_audio_file(job_id: str, filename: str):
    """音声ファイルを取得。"""
    # ファイル名サニタイズ（パストラバーサル対策）
    safe_name = Path(filename).name
    if not safe_name or ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="不正なファイル名です")

    audio_path = Path.cwd() / "audio" / job_id / safe_name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="音声ファイルが見つかりません")

    # 念のため job_id ディレクトリ配下であることを確認
    base_audio_dir = (Path.cwd() / "audio" / job_id).resolve()
    try:
        audio_path.resolve().relative_to(base_audio_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="アクセスが拒否されました")

    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{safe_name}"',
        },
    )


@router.get("/{job_id}/download")
async def download_video(job_id: str):
    """完成した動画をダウンロード。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs_db[job_id]
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="動画が完成していません")

    video_path = OUTPUT_DIR / f"{job_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"video_{job_id}.mp4",
    )
