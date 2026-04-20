"""対話スクリプト関連のルート（取得・CSV・更新・生成）。"""
import csv
import io
import json
import shutil
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import BackgroundTasks, File, HTTPException, Response, UploadFile

from api.core.async_worker import async_worker
from api.core.status_codes import StatusCode
from api.models.job import GenerateDialogueRequest, UpdateDialogueRequest

from ._shared import (
    UPLOAD_DIR,
    estimate_video_duration,
    format_duration,
    jobs_db,
    router,
)


@router.post("/{job_id}/generate-dialogue")
async def generate_dialogue_only(
    job_id: str,
    request: GenerateDialogueRequest,
    background_tasks: BackgroundTasks,
):
    """対話スクリプトのみを生成。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs_db[job_id]

    if job.status not in ["slides_ready", "dialogue_ready", "completed"]:
        if job.status == "generating_dialogue":
            print(f"エラー: 対話生成が進行中です。ジョブID: {job_id}")
            raise HTTPException(status_code=400, detail="対話生成が進行中です。完了までお待ちください。")
        elif job.status == "failed":
            print(f"エラー: 前回の処理が失敗しています。ジョブID: {job_id}")
            raise HTTPException(status_code=400, detail="前回の処理が失敗しています")
        else:
            print(f"エラー: 対話生成できない状態です。ジョブID: {job_id}, ステータス: {job.status}")
            raise HTTPException(status_code=400, detail=f"対話生成できない状態です: {job.status}")

    if request.additional_prompt:
        task_id = f"dialogue_regen_{job_id}_{int(time.time())}"
    else:
        task_id = f"dialogue_{job_id}"

    if not request.additional_prompt and async_worker.is_task_running(task_id):
        raise HTTPException(status_code=409, detail="対話生成が既に実行中です")

    job.status = "generating_dialogue"
    job.status_code = StatusCode.DIALOGUE_GENERATING
    job.progress = 30
    job.updated_at = datetime.now()

    from api.core.job_processor import JobProcessor  # lazy: 内部で重い依存を持つ
    await async_worker.submit_task(
        task_id,
        JobProcessor.generate_dialogue_sync,
        job_id, request.additional_prompt, jobs_db, request.api_key, request.provider,
    )

    return {"message": "対話スクリプト生成を開始しました（非同期処理）", "job_id": job_id}


@router.get("/{job_id}/dialogue")
async def get_dialogue(job_id: str):
    """生成された対話スクリプトを取得。"""
    dialogue_path = Path.cwd() / "data" / job_id / "dialogue_narration_original.json"
    if not dialogue_path.exists():
        raise HTTPException(status_code=404, detail="対話スクリプトが見つかりません")

    with open(dialogue_path, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    total_seconds = estimate_video_duration(dialogue_data)
    return {
        "dialogue_data": dialogue_data,
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds),
        },
    }


@router.get("/{job_id}/dialogue/timing")
async def get_dialogue_timing(job_id: str):
    """各対話の音声ファイルの実長（秒）を返す。"""
    data_dir = Path.cwd() / "data" / job_id
    dialogue_path = data_dir / "dialogue_narration_original.json"
    audio_dir = Path.cwd() / "audio" / job_id

    if not dialogue_path.exists():
        raise HTTPException(status_code=404, detail="対話スクリプトが見つかりません")

    with open(dialogue_path, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    result: Dict[str, List[Dict]] = {}
    for slide_key in sorted(dialogue_data.keys(), key=lambda x: int(x.split("_")[1])):
        dialogues = dialogue_data[slide_key]
        result[slide_key] = []
        slide_num = int(slide_key.split("_")[1])
        for idx, d in enumerate(dialogues):
            speaker = d.get("speaker", "speaker1")
            wav_name = f"slide_{slide_num:03d}_{idx + 1:03d}_{speaker}.wav"
            wav_path = audio_dir / wav_name
            duration_sec = None
            if wav_path.exists():
                try:
                    with wave.open(str(wav_path), "rb") as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration_sec = round(frames / float(rate), 2)
                except Exception:
                    pass
            result[slide_key].append({"duration": duration_sec})
    return result


@router.get("/{job_id}/dialogue/csv")
async def download_dialogue_csv(job_id: str):
    """対話スクリプトをCSV形式でダウンロード。"""
    dialogue_path = Path.cwd() / "data" / job_id / "dialogue_narration_original.json"
    if not dialogue_path.exists():
        raise HTTPException(status_code=404, detail="対話スクリプトが見つかりません")

    with open(dialogue_path, "r", encoding="utf-8") as f:
        dialogue_data = json.load(f)

    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(["会話番号", "スライド番号", "発話者名", "テキスト"])

    metadata_path = UPLOAD_DIR / job_id / "metadata.json"
    speaker1_name = "四国めたん"
    speaker2_name = "ずんだもん"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            speaker1_name = metadata.get("speaker1", {}).get("name", "四国めたん")
            speaker2_name = metadata.get("speaker2", {}).get("name", "ずんだもん")

    conversation_num = 0
    for slide_key in sorted(dialogue_data.keys(), key=lambda x: int(x.split("_")[1])):
        slide_num = slide_key.split("_")[1]
        for dialogue in dialogue_data[slide_key]:
            conversation_num += 1
            if dialogue["speaker"] in ("speaker1", "metan"):
                speaker_display = speaker1_name
            elif dialogue["speaker"] in ("speaker2", "zundamon"):
                speaker_display = speaker2_name
            else:
                speaker_display = dialogue["speaker"]
            csv_writer.writerow([conversation_num, slide_num, speaker_display, dialogue["text"]])

    csv_content = csv_buffer.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dialogue_{job_id}.csv"},
    )


@router.post("/{job_id}/dialogue/csv")
async def upload_dialogue_csv(job_id: str, file: UploadFile = File(...)):
    """CSVファイルから対話スクリプトをアップロード。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSVファイルのみ対応しています")

    content = await file.read()
    csv_text = None
    for enc in ("utf-8-sig", "utf-8", "shift-jis", "cp932"):
        try:
            csv_text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if csv_text is None:
        raise HTTPException(
            status_code=400,
            detail="CSVファイルのエンコーディングが不正です（UTF-8、Shift-JIS、またはCP932を使用してください）",
        )

    csv_reader = csv.DictReader(io.StringIO(csv_text))

    metadata_path = UPLOAD_DIR / job_id / "metadata.json"
    speaker1_name = "四国めたん"
    speaker2_name = "ずんだもん"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            speaker1_name = metadata.get("speaker1", {}).get("name", "四国めたん")
            speaker2_name = metadata.get("speaker2", {}).get("name", "ずんだもん")

    dialogue_data: Dict[str, List[Dict]] = {}
    errors: List[str] = []
    required_columns = ["会話番号", "スライド番号", "発話者名", "テキスト"]

    for line_num, row in enumerate(csv_reader, start=2):
        missing_columns = [col for col in required_columns if col not in row]
        if missing_columns:
            errors.append(f"行{line_num}: 必要な列がありません: {', '.join(missing_columns)}")
            continue

        conversation_num = row.get("会話番号", "").strip()
        slide_num = row.get("スライド番号", "").strip()
        speaker_display = row.get("発話者名", "").strip()
        text = row.get("テキスト", "").strip()

        try:
            if int(conversation_num) < 1:
                errors.append(f"行{line_num}: 会話番号は1以上である必要があります")
                continue
        except ValueError:
            errors.append(f"行{line_num}: 会話番号が数値ではありません: {conversation_num}")
            continue

        try:
            slide_num_int = int(slide_num)
            if slide_num_int < 1:
                errors.append(f"行{line_num}: スライド番号は1以上である必要があります")
                continue
        except ValueError:
            errors.append(f"行{line_num}: スライド番号が数値ではありません: {slide_num}")
            continue

        if speaker1_name in speaker_display or speaker_display in speaker1_name:
            speaker = "speaker1"
        elif speaker2_name in speaker_display or speaker_display in speaker2_name:
            speaker = "speaker2"
        elif speaker_display.lower() in ("speaker1", "キャラ1", "キャラクター1"):
            speaker = "speaker1"
        elif speaker_display.lower() in ("speaker2", "キャラ2", "キャラクター2"):
            speaker = "speaker2"
        else:
            errors.append(
                f"行{line_num}: 発話者名が不正です（'{speaker1_name}'または'{speaker2_name}'である必要があります）: '{speaker_display}'"
            )
            continue

        if not text:
            errors.append(f"行{line_num}: テキストが空です")
            continue

        slide_key = f"slide_{slide_num_int}"
        dialogue_data.setdefault(slide_key, []).append({"speaker": speaker, "text": text})

    if errors:
        error_message = "CSVファイルに以下のエラーがあります:\n" + "\n".join(errors[:10])
        if len(errors) > 10:
            error_message += f"\n... 他{len(errors)-10}個のエラー"
        raise HTTPException(status_code=400, detail=error_message)

    if not dialogue_data:
        raise HTTPException(status_code=400, detail="有効な対話データが含まれていません")

    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)

    dialogue_path = data_dir / "dialogue_narration_original.json"
    with open(dialogue_path, "w", encoding="utf-8") as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    katakana_path = data_dir / "dialogue_narration_katakana.json"
    with open(katakana_path, "w", encoding="utf-8") as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    audio_dir = Path.cwd() / "audio" / job_id
    if audio_dir.exists():
        shutil.rmtree(audio_dir)
        print(f"既存の音声ファイルを削除しました: {audio_dir}")

    job = jobs_db[job_id]
    job.status = "dialogue_ready"
    job.status_code = StatusCode.DIALOGUE_COMPLETED
    job.updated_at = datetime.now()

    total_seconds = estimate_video_duration(dialogue_data)
    return {
        "message": f"対話スクリプトをインポートしました（{len(dialogue_data)}スライド）",
        "slide_count": len(dialogue_data),
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds),
        },
    }


@router.put("/{job_id}/dialogue")
async def update_dialogue(job_id: str, request: UpdateDialogueRequest):
    """対話スクリプトを更新。"""
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    data_dir = Path.cwd() / "data" / job_id
    data_dir.mkdir(exist_ok=True)

    dialogue_path = data_dir / "dialogue_narration_original.json"
    katakana_path = data_dir / "dialogue_narration_katakana.json"

    with open(dialogue_path, "w", encoding="utf-8") as f:
        json.dump(request.dialogue_data, f, ensure_ascii=False, indent=2)
    with open(katakana_path, "w", encoding="utf-8") as f:
        json.dump(request.dialogue_data, f, ensure_ascii=False, indent=2)

    audio_dir = Path.cwd() / "audio" / job_id
    if audio_dir.exists():
        shutil.rmtree(audio_dir)
        print(f"既存の音声ファイルを削除しました: {audio_dir}")

    job = jobs_db[job_id]
    job.status = "dialogue_ready"
    job.status_code = StatusCode.DIALOGUE_COMPLETED
    job.updated_at = datetime.now()

    total_seconds = estimate_video_duration(request.dialogue_data)
    return {
        "message": "対話スクリプトを更新しました",
        "estimated_duration": {
            "seconds": total_seconds,
            "formatted": format_duration(total_seconds),
        },
    }
