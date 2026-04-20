"""API のスモークテスト。

重い外部依存（VOICEVOX, LLM, moviepy など）は一切呼ばない範囲で、
ルーティングと基本バリデーションの健全性を検証する。
"""
import io


def test_root_returns_service_info(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Gen Movie API"
    assert "version" in body


def test_list_jobs_returns_empty_initially(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_status_for_unknown_job_returns_404(client):
    r = client.get("/api/jobs/does-not-exist/status")
    assert r.status_code == 404


def test_delete_unknown_job_returns_404(client):
    r = client.delete("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_upload_rejects_non_pdf_extension(client):
    files = {"file": ("note.txt", io.BytesIO(b"not a pdf"), "text/plain")}
    r = client.post("/api/jobs/upload", files=files)
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_upload_rejects_content_without_pdf_magic(client):
    # 拡張子は .pdf だが中身が PDF ヘッダではない
    files = {"file": ("fake.pdf", io.BytesIO(b"NOT-A-PDF"), "application/pdf")}
    r = client.post("/api/jobs/upload", files=files)
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_upload_rejects_invalid_target_duration(client):
    files = {"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n..."), "application/pdf")}
    r = client.post("/api/jobs/upload", files=files, data={"target_duration": "9999"})
    assert r.status_code == 400


def test_upload_rejects_invalid_provider(client):
    files = {"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n..."), "application/pdf")}
    r = client.post("/api/jobs/upload", files=files, data={"provider": "hacker-llm"})
    assert r.status_code == 400


def test_upload_rejects_invalid_speaker_speed(client):
    files = {"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n..."), "application/pdf")}
    r = client.post("/api/jobs/upload", files=files, data={"speaker1_speed": "9.0"})
    assert r.status_code == 400


def test_cors_default_is_wildcard(client):
    # デフォルトの環境では allow_origins=["*"]
    r = client.get("/", headers={"Origin": "http://example.com"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_slide_image_404_when_missing(client):
    r = client.get("/api/jobs/no-such-job/slides/1")
    assert r.status_code == 404


def test_get_dialogue_404_when_missing(client):
    r = client.get("/api/jobs/no-such-job/dialogue")
    assert r.status_code == 404
