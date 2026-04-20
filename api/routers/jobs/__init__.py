"""jobs ルーターパッケージ。

後方互換のため `router` と `jobs_db` をトップレベルに公開する。
サブモジュールを import することで全ルートが `router` に登録される。
"""
from ._shared import (
    OUTPUT_DIR,
    UPLOAD_DIR,
    estimate_video_duration,
    format_duration,
    jobs_db,
    router,
)

# サブモジュールを import して @router.* デコレータを発火させる
from . import crud  # noqa: E402,F401
from . import dialogue  # noqa: E402,F401
from . import generation  # noqa: E402,F401
from . import media  # noqa: E402,F401
from . import slides  # noqa: E402,F401
from . import uploads  # noqa: E402,F401

# パイプライン関数を公開（既存呼び出しコードとの互換性のため）
from ._pipeline import (  # noqa: E402,F401
    convert_pdf_to_slides,
    create_video_task,
    generate_audio_task,
    generate_complete_video,
)

__all__ = [
    "OUTPUT_DIR",
    "UPLOAD_DIR",
    "convert_pdf_to_slides",
    "create_video_task",
    "estimate_video_duration",
    "format_duration",
    "generate_audio_task",
    "generate_complete_video",
    "jobs_db",
    "router",
]
