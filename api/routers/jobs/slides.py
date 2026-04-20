"""スライド関連のルート。"""
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from api.models.job import SlideImportanceRequest

from ._shared import jobs_db, router


@router.get("/{job_id}/slides")
async def get_slides(job_id: str):
    """スライド画像のリストを取得。"""
    slides_dir = Path.cwd() / "slides" / job_id
    if not slides_dir.exists():
        raise HTTPException(status_code=404, detail="スライドが見つかりません")

    slides = []
    for slide_path in sorted(slides_dir.glob("slide_*.png")):
        slide_num = int(slide_path.stem.split("_")[1])
        slides.append({
            "slide_number": slide_num,
            "url": f"/api/jobs/{job_id}/slides/{slide_num}",
        })
    return slides


@router.get("/{job_id}/slides/{slide_number}")
async def get_slide_image(job_id: str, slide_number: int):
    """特定のスライド画像を取得。"""
    slide_path = Path.cwd() / "slides" / job_id / f"slide_{slide_number:03d}.png"
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="スライド画像が見つかりません")
    return FileResponse(path=slide_path, media_type="image/png")


@router.put("/{job_id}/slide-importance")
async def update_slide_importance(job_id: str, request: SlideImportanceRequest):
    """スライド重要度を設定。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)
    importance_path = data_dir / "slide_importance.json"

    validated_importance = {}
    for slide_num, importance in request.importance_map.items():
        if 0.5 <= importance <= 1.5:
            validated_importance[slide_num] = importance
        else:
            raise HTTPException(
                status_code=400,
                detail=f"スライド{slide_num}の重要度は0.5〜1.5の範囲で指定してください",
            )

    with open(importance_path, "w", encoding="utf-8") as f:
        json.dump(validated_importance, f, ensure_ascii=False, indent=2)

    return {
        "message": "スライド重要度を更新しました",
        "importance_map": validated_importance,
    }


@router.get("/{job_id}/slide-importance")
async def get_slide_importance(job_id: str):
    """スライド重要度を取得。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    importance_path = Path.cwd() / "data" / job_id / "slide_importance.json"
    if importance_path.exists():
        with open(importance_path, "r", encoding="utf-8") as f:
            importance_map = json.load(f)
            return {int(k): float(v) for k, v in importance_map.items()}
    return {}
