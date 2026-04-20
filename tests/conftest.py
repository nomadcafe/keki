"""pytest 共通フィクスチャ。

テストはプロジェクト固有のワーキングディレクトリ配下で動く想定。
各テスト間で DB を汚さないよう、`data/` 配下に隔離した一時 DB を使う。
"""
import os
import sys
from pathlib import Path

import pytest

# プロジェクトルートを sys.path に追加（tests/ から api を import できるように）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient を返す。作業ディレクトリは tmp に隔離。"""
    monkeypatch.chdir(tmp_path)
    # DB 初期化が data/ に対して行われるので、tmp 配下に用意
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "uploads").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    # SettingsManager は docker-compose.yml を辿ってプロジェクトルートを決める。
    # tmp_path にマーカーを置いて探索が外に漏れないようにする。
    (tmp_path / "docker-compose.yml").write_text("# test marker\n")
    (tmp_path / ".env").write_text("")

    # CORS の確定的な挙動を見るためデフォルト（*）を使う
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    # app はモジュールキャッシュに残るので、DB は tmp でも __init__ 時の
    # Path.cwd() 解決に依存。fresh に読むためキャッシュをクリア。
    for mod in list(sys.modules):
        if mod.startswith("api."):
            del sys.modules[mod]

    from fastapi.testclient import TestClient
    from api.main import app
    from api.database.db import init_db

    init_db()
    with TestClient(app) as c:
        yield c
