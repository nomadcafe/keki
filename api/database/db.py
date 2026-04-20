"""
データベース接続とセッション管理
"""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from api.database.models import Base

# データベースファイルのパス
# Docker環境では /app/data、ローカルでは ./data
BASE_DIR = Path.cwd()
if (BASE_DIR / "data").exists() or str(BASE_DIR).endswith("/app"):
    # Docker環境または既にdataディレクトリが存在する場合
    DB_DIR = BASE_DIR / "data"
else:
    # ローカル環境
    DB_DIR = BASE_DIR / "data"

DB_DIR.mkdir(exist_ok=True, parents=True)
DB_PATH = DB_DIR / "kekiai.db"

# SQLiteデータベースエンジンを作成
# check_same_thread=False は SQLite のスレッド安全性を無効化（FastAPIの非同期処理で必要）
DATABASE_URL = f"sqlite:///{DB_PATH.absolute()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """SQLite 接続時に並行性・安全性向上の PRAGMA を設定。

    - WAL: 書き込み中でも読み取りがブロックされない
    - busy_timeout: ロック待ちで即エラーにせず 5 秒待つ
    - foreign_keys: 外部キー制約を有効化
    - synchronous=NORMAL: WAL と組み合わせて安全性と性能のバランス
    """
    # sqlite3 以外の接続（テストで別 DB 使う場合など）に誤発動しないようガード
    try:
        import sqlite3
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
    except ImportError:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()

# セッションファクトリーを作成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """データベースを初期化（テーブルを作成）"""
    Base.metadata.create_all(bind=engine)
    print(f"データベースを初期化しました: {DB_PATH}")


def get_db() -> Generator[Session, None, None]:
    """
    データベースセッションを取得（依存性注入用）
    使用例:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """
    データベースセッションを直接取得（バックグラウンドタスク用）
    使用後は必ず close() を呼び出すこと
    使用例:
        db = get_db_session()
        try:
            # データベース操作
            ...
        finally:
            db.close()
    """
    return SessionLocal()

