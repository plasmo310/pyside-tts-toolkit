"""ツールの設定と、3 つのエンジンの定義。

ここには 2 種類の設定が入っている。

1. `ToolConfig` ... GUI の見た目・保存先・リソースのパス
2. `ENGINE_DEFINITIONS` ... どのモデルをどの仮想環境で動かすかの定義

画面に並べる選択肢は `definitions.py` に置いてある。Qt には依存しない
ので、CLI からもそのまま import できる。
"""

from __future__ import annotations

import os
import sys

from ttstoolkit.definitions import EngineType
from ttstoolkit.engine.paths import PYTHON_DIR, ROOT_DIR, venv_python
from ttstoolkit.engine.settings import IS_WINDOWS
from ttstoolkit.engine.types import Capability, EngineSpec

# スタイルシートの中で resources/ の絶対パスに置き換えるプレースホルダ
_RESOURCES_DIR_PLACEHOLDER = "{RESOURCES_DIR}"

# Irodori は PyPI 未公開で、依存の dacvae も PyPI に無い。上流リポジトリを
# clone したものを検索パスに足して import する。
_IRODORI_VENDOR = os.path.join(
    ROOT_DIR, "engine_env", "irodori", "vendor", "Irodori-TTS"
)


class ToolConfig:
    """ツール設定クラス"""

    # ツールタイトル
    TOOL_TITLE = "TTS Toolkit"

    # ウィンドウの既定サイズ
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 880

    # 入力行の高さ (全部揃えて縦位置をきれいに出す)
    ROW_HEIGHT = 28

    # Cancel / Run ボタンの幅
    # 高さはタブと揃えるため stylesheet.qss 側で指定している
    CANCEL_BUTTON_WIDTH = 110

    # 入力行の左に置くラベルの幅 (タブ間で揃える)
    LABEL_WIDTH = 150

    # 台詞やボイス指示を書き込む複数行入力の高さ。
    # 1 タブに 2 つ並ぶので、全部の行が一度に見える高さに抑える。
    TEXT_EDIT_HEIGHT = 84

    # QSettings の識別子
    SETTINGS_ORGANIZATION = "TTSToolkit"
    SETTINGS_APPLICATION = "TTSToolkit"

    # 参照音声の選択ダイアログのフィルタ
    AUDIO_FILE_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg);;All Files (*)"

    # 台本ファイル選択ダイアログのフィルタ
    SCRIPT_FILE_FILTER = "Text (*.txt);;All Files (*)"

    # キャスト定義ファイル選択ダイアログのフィルタ
    CAST_FILE_FILTER = "TOML (*.toml);;All Files (*)"

    @staticmethod
    def __get_resources_dir() -> str:
        """resources/ の絶対パスを返す。

        PyInstaller で固めた場合は `_internal/resources/` を見る。
        参考: https://pyinstaller.org/en/stable/runtime-information.html
        """
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, "resources")
        return os.path.join(ROOT_DIR, "resources")

    @staticmethod
    def get_tool_icon_path() -> str:
        """ツールアイコンのパスを返す。

        置いていなければ空文字を返す (Qt は既定のアイコンを使う)。

        Returns:
            str: アイコンのパス。無ければ空文字。
        """
        file_name = (
            "tool_icon_rect.ico" if IS_WINDOWS else "tool_icon_round.icns"
        )
        path = os.path.join(
            ToolConfig.__get_resources_dir(), "icon", file_name
        )
        return path if os.path.isfile(path) else ""

    @staticmethod
    def load_stylesheet() -> str:
        """スタイルシートを読み込む。

        QSS の `url()` は実行時のカレントディレクトリ基準で解決されて
        しまうので、`{RESOURCES_DIR}` を resources/ の絶対パスに
        置き換えてから返す。区切りは QSS が解釈できるスラッシュにする。

        Returns:
            str: スタイルシートの中身。読めなければ空文字。
        """
        resources_dir = ToolConfig.__get_resources_dir()
        stylesheet_path = os.path.join(resources_dir, "ui", "stylesheet.qss")
        if not os.path.isfile(stylesheet_path):
            return ""

        try:
            with open(stylesheet_path, encoding="utf-8") as file:
                stylesheet = file.read()
        except UnicodeDecodeError:
            with open(stylesheet_path, encoding="utf-8-sig") as file:
                stylesheet = file.read()

        return stylesheet.replace(
            _RESOURCES_DIR_PLACEHOLDER, resources_dir.replace("\\", "/")
        )


# ---------------------------------------------------------------------------
# エンジンの定義
#
# 3 モデルは transformers / torch のピンが互いに排他的で、1 つの仮想環境には
# 同居できない。エンジンごとに仮想環境を持ち、共通層はサブプロセス越しに
# runner を呼ぶ。
#
#   qwen       : transformers==4.57.3
#   chatterbox : transformers==5.2.0, torch==2.6.0 (Blackwell 対応で上書き)
#   irodori    : transformers>=5.12.1, torch>=2.10
#
# 仮想環境の定義は engine_env/<name>/pyproject.toml、実体は .venvs/engine-*。
# 構築手順は scripts/win/setup_engines.ps1 を参照。
# ---------------------------------------------------------------------------

ENGINE_DEFINITIONS: dict[str, EngineSpec] = {
    EngineType.QWEN.value: EngineSpec(
        name=EngineType.QWEN.value,
        description=(
            "Qwen3-TTS 1.7B - high quality in both Japanese and English; "
            "3-second cloning and voice design"
        ),
        capabilities=(
            Capability.CLONE
            | Capability.SEED
            | Capability.MULTILINGUAL
            | Capability.VOICE_DESIGN
        ),
        languages=("ja", "en"),
        model_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        python=venv_python("engine-qwen"),
        runner="ttstoolkit.engine.runners.qwen_runner",
        cwd=ROOT_DIR,
        setup_doc="01_qwen3-tts.md",
        python_path=(PYTHON_DIR,),
        options={
            # 参照音声ありのときに使うクローンモデル。
            # VRAM が足りなければ 0.6B に下げる。
            "base_model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            # 参照音声なしのときに使うプリセット話者モデル。
            "custom_voice_model": ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
            # 文章から架空の声を作るときに使うモデル。
            "voice_design_model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            # CustomVoice が持つ話者は aiden, dylan, eric, ono_anna,
            # ryan, serena, sohee, uncle_fu, vivian の 9 名。
            "default_speaker": "ono_anna",
            "speakers": {"ja": "ono_anna", "en": "ryan"},
            "dtype": "bfloat16",
            "device": "cuda:0",
            # flash_attention_2 は Windows でビルドが通らないため sdpa。
            "attn_implementation": "sdpa",
            "max_new_tokens": 2048,
        },
    ),
    EngineType.CHATTERBOX.value: EngineSpec(
        name=EngineType.CHATTERBOX.value,
        description=(
            "Chatterbox Multilingual V3 - 0.5B, 23 languages, "
            "the lightest to set up"
        ),
        capabilities=(
            Capability.CLONE | Capability.SEED | Capability.MULTILINGUAL
        ),
        languages=("ja", "en"),
        model_id="ResembleAI/chatterbox (multilingual v3)",
        python=venv_python("engine-chatterbox"),
        runner="ttstoolkit.engine.runners.chatterbox_runner",
        cwd=ROOT_DIR,
        setup_doc="02_chatterbox.md",
        python_path=(PYTHON_DIR,),
        options={
            "t3_model": "v3",
            "device": "cuda",
            "exaggeration": 0.5,
            "cfg_weight": 0.5,
            "temperature": 0.8,
        },
    ),
    EngineType.IRODORI.value: EngineSpec(
        name=EngineType.IRODORI.value,
        description=(
            "Irodori-TTS v4.1 Small - Japanese only, 48 kHz, "
            "strong at voice design and emotion"
        ),
        capabilities=(
            Capability.CLONE
            | Capability.SEED
            | Capability.SPEED
            | Capability.VOICE_DESIGN
        ),
        languages=("ja",),
        model_id="Aratako/Irodori-TTS-v4.1-Small",
        python=venv_python("engine-irodori"),
        runner="ttstoolkit.engine.runners.irodori_runner",
        # 上流リポジトリは相対パスで作業ファイルを置くので clone の中で動かす。
        cwd=_IRODORI_VENDOR,
        setup_doc="03_irodori-tts.md",
        python_path=(PYTHON_DIR, _IRODORI_VENDOR),
        options={
            "hf_checkpoint": "Aratako/Irodori-TTS-v4.1-Small",
            "codec_repo": "Aratako/Semantic-DACVAE-Japanese-32dim",
            "model_precision": "fp32",
            "num_steps": 24,
            "cfg_guidance_mode": "independent",
            "cfg_scale_text": 3.0,
            "cfg_scale_caption": 3.0,
            "cfg_scale_speaker": 5.0,
        },
    ),
}
